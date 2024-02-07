from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Generator

import colorama
import pytest

from .data import MultihostItemData
from .logging import MultihostLogger
from .marks import TopologyMark
from .misc import invoke_callback
from .multihost import MultihostConfig, MultihostDomain, MultihostHost, MultihostRole
from .topology import Topology, TopologyDomain
from .topology_controller import TopologyController


class MultihostFixture(object):
    """
    Multihost object provides access to underlaying multihost configuration,
    individual domains and hosts. This object should be used only in tests
    as the :func:`mh` pytest fixture.

    Domains are accessible as dynamically created properties of this object,
    hosts are accessible by roles as dynamically created properties of each
    domain. Each host object is instance of specific role class based on
    :mod:`~pytest_mh.MultihostRole`.

    .. code-block:: yaml
        :caption: Example multihost configuration

        domains:
        - id: test
          hosts:
          - name: client
            hostname: client.test
            role: client

          - name: ldap
            hostname: master.ldap.test
            role: ldap

    The configuration above creates one domain of id ``test`` with two hosts.
    The following example shows how to access the hosts:

    .. code-block:: python
        :caption: Example of the MultihostFixture object

        def test_example(mh: MultihostFixture):
            mh.ns.test            # -> namespace containing roles as properties
            mh.ns.test.client     # -> list of hosts providing given role
            mh.ns.test.client[0]  # -> host object, instance of specific role
    """

    def __init__(
        self,
        request: pytest.FixtureRequest,
        data: MultihostItemData,
        multihost: MultihostConfig,
        topology_mark: TopologyMark,
    ) -> None:
        """
        :param request: Pytest request.
        :type request: pytest.FixtureRequest
        :param data: Multihost item data.
        :type data: MultihostItemData
        :param multihost: Multihost configuration.
        :type multihost: MultihostConfig
        :param topology_mark: Multihost topology mark.
        :type topology_mark: TopologyMark
        """

        self.data: MultihostItemData = data
        """
        Multihost item data.
        """

        self.request: pytest.FixtureRequest = request
        """
        Pytest request.
        """

        self.multihost: MultihostConfig = multihost
        """
        Multihost configuration.
        """

        self.topology_mark: TopologyMark = topology_mark
        """
        Topology mark.
        """

        self.topology: Topology = topology_mark.topology
        """
        Topology data.
        """

        self.topology_controller: TopologyController = topology_mark.controller
        """
        Topology controller.
        """

        self.logger: MultihostLogger = multihost.logger
        """
        Multihost logger.
        """

        self.roles: list[MultihostRole] = []
        """
        Available MultihostRole objects.
        """

        self.hosts: list[MultihostHost] = []
        """
        Available MultihostHost objects.
        """

        self.ns: SimpleNamespace = SimpleNamespace()
        """
        Roles as object accessible through topology path, e.g. ``mh.ns.domain_id.role_name``.
        """

        self._opt_artifacts_dir: str = self.request.config.getoption("mh_artifacts_dir")
        self._opt_artifacts_mode: str = self.request.config.getoption("mh_collect_artifacts")
        self._opt_artifacts_compression: bool = self.request.config.getoption("mh_compress_artifacts")

        self._paths: dict[str, list[MultihostRole] | MultihostRole] = {}
        self._skipped: bool = False

        for domain in self.multihost.domains:
            if domain.id in self.topology:
                setattr(self.ns, domain.id, self._domain_to_namespace(domain, self.topology.get(domain.id)))

        self.roles = sorted([x for x in self._paths.values() if isinstance(x, MultihostRole)], key=lambda x: x.role)
        self.hosts = sorted(list({x.host for x in self.roles}), key=lambda x: x.hostname)

    def _domain_to_namespace(self, domain: MultihostDomain, topology_domain: TopologyDomain) -> SimpleNamespace:
        ns = SimpleNamespace()
        for role_name in domain.roles:
            if role_name not in topology_domain:
                continue

            count = topology_domain.get(role_name)
            roles = [domain.create_role(self, host) for host in domain.hosts_by_role(role_name)[:count]]

            self._paths[f"{domain.id}.{role_name}"] = roles
            for index, role in enumerate(roles):
                self._paths[f"{domain.id}.{role_name}[{index}]"] = role

            setattr(ns, role_name, roles)

        return ns

    def _lookup(self, path: str) -> MultihostRole | list[MultihostRole]:
        """
        Lookup host by path. The path format is ``$domain.$role``
        or ``$domain.$role[$index]``

        :param path: Host path.
        :type path: str
        :raises LookupError: If host is not found.
        :return: The role object if index was given, list of role objects otherwise.
        :rtype: MultihostRole | list[MultihostRole]
        """

        if path not in self._paths:
            raise LookupError(f'Name "{path}" does not exist')

        return self._paths[path]

    def _skip(self) -> bool:
        self._skipped = False

        reason = self._skip_by_topology(self.topology_controller)
        if reason is not None:
            self._skipped = True
            pytest.skip(reason)

        reason = self._skip_by_require_marker(self.topology_mark, self.request.node)
        if reason is not None:
            self._skipped = True
            pytest.skip(reason)

        return self._skipped

    def _skip_by_topology(self, controller: TopologyController):
        return controller._invoke_with_args(controller.skip)

    def _skip_by_require_marker(self, topology_mark: TopologyMark, node: pytest.Function) -> str | None:
        fixtures: dict[str, Any] = {k: None for k in topology_mark.fixtures.keys()}
        fixtures.update(node.funcargs)
        topology_mark.apply(self, fixtures)

        # Make sure mh fixture is always available
        fixtures["mh"] = self

        for mark in node.iter_markers("require"):
            if len(mark.args) not in [1, 2]:
                raise ValueError(f"{node.nodeid}::{node.originalname}: " "invalid arguments for @pytest.mark.require")

            condition = mark.args[0]
            reason = "Required condition was not met" if len(mark.args) != 2 else mark.args[1]

            callresult = invoke_callback(condition, **fixtures)
            if isinstance(callresult, tuple):
                if len(callresult) != 2:
                    raise ValueError(
                        f"{node.nodeid}::{node.originalname}: " "invalid arguments for @pytest.mark.require"
                    )

                result = callresult[0]
                reason = callresult[1]
            else:
                result = callresult

            if not result:
                return reason

        return None

    def _topology_setup(self) -> None:
        """
        Run per-test setup from topology controller.
        """
        if self._skipped:
            return

        self.topology_controller._invoke_with_args(self.topology_controller.setup)
        self.topology_controller._op_state.set_success("setup")

    def _topology_teardown(self) -> None:
        """
        Run per-test teardown from topology controller.
        """
        if self._skipped:
            return

        if self.topology_controller._op_state.check_success("setup"):
            self.topology_controller._invoke_with_args(self.topology_controller.teardown)

    def _setup(self) -> None:
        """
        Setup multihost. A setup method is called on each host and role
        to initialize the test environment to expected state.
        """
        if self._skipped:
            return

        for item in self.hosts + self.roles:
            item.setup()
            item._op_state.set_success("setup")

    def _teardown(self) -> None:
        """
        Teardown multihost. The purpose of this method is to revert any changes
        that were made during a test run. It is automatically called when the
        test is finished.
        """
        if self._skipped:
            return

        # Create list of dynamically added artifacts
        additional_artifacts: dict[MultihostHost, list[str]] = {}
        for role in self.roles:
            additional_artifacts.setdefault(role.host, []).extend(role.artifacts)

        errors = []

        # Collect artifacts, it an error is raised, we will ignore it since
        # teardown is more important
        for host in self.hosts:
            try:
                self._collect_artifacts(host, additional_artifacts[host])
            except Exception as e:
                errors.append(e)

        for item in self.roles + self.hosts:
            if item._op_state.check_success("setup"):
                try:
                    item.teardown()
                except Exception as e:
                    errors.append(e)

        if errors:
            raise Exception(errors)

    def _artifacts_dir(self) -> str | None:
        """
        Return test artifact directory or ``None`` if no artifacts should be
        stored.

        :return: Artifact directory or ``None``.
        :rtype: str | None
        """
        if self._skipped:
            return None

        dir = self._opt_artifacts_dir
        mode = self._opt_artifacts_mode

        # There was error in fixture setup if the outcome is not known at this point
        outcome = self.data.outcome if self.data.outcome is not None else "error"
        if mode == "never" or (mode == "on-failure" and outcome not in ("failed", "error")):
            return None

        name = self.request.node.name
        name = name.translate(str.maketrans('":<>|*? [', "---------", "]()"))

        return f"{dir}/{name}"

    def _collect_artifacts(self, host: MultihostHost, artifacts: list[str]) -> None:
        """
        Collect test artifacts that were requested by the multihost
        configuration.

        :param host: Host object where the artifacts will be collected.
        :type host: MultihostHost
        :param artifacts: Additional artifacts that will be fetched together
            with artifacts from configuration file.
        :type artifacts: list[str]
        """
        path = self._artifacts_dir()
        if path is None:
            return

        host.collect_artifacts(path, artifacts, self._opt_artifacts_compression)

    def _flush_logs(self) -> None:
        """
        Write log messages produced by current test case to a file, or clear
        them if no artifacts should be generated.
        """
        path = self._artifacts_dir()
        if path is None:
            self.logger.clear()
        else:
            self.logger.write_to_file(f"{path}/test.log")

    def _invoke_phase(self, name: str, cb: Callable, catch: bool = False) -> Exception | None:
        self.log_phase(name)
        try:
            cb()
        except Exception as e:
            if catch:
                return e

            raise
        finally:
            self.log_phase(f"{name} DONE")

        return None

    def log_phase(self, phase: str) -> None:
        """
        Log current test phase.

        :param phase: Phase name or description.
        :type phase: str
        """
        self.logger.info(
            self.logger.colorize(
                f"{phase} :: {self.request.node.nodeid}",
                colorama.Style.BRIGHT,
                colorama.Back.BLACK,
                colorama.Fore.WHITE,
            )
        )

    def _enter(self) -> MultihostFixture:
        if self._skip():
            return self

        self.log_phase("BEGIN")
        self._invoke_phase("SETUP TOPOLOGY", self._topology_setup)
        self._invoke_phase("SETUP TEST", self._setup)

        return self

    def _exit(self) -> None:
        errors: list[Exception | None] = []
        errors.append(self._invoke_phase("TEARDOWN TEST", self._teardown, catch=True))
        errors.append(self._invoke_phase("TEARDOWN TOPOLOGY", self._topology_teardown, catch=True))

        self.log_phase("END")
        self._flush_logs()

        errors = [x for x in errors if x is not None]
        if errors:
            raise Exception(errors)


@pytest.fixture(scope="function")
def mh(request: pytest.FixtureRequest) -> Generator[MultihostFixture, None, None]:
    """
    Pytest multihost fixture. Returns instance of :class:`MultihostFixture`.
    When a pytest test is finished, this fixture takes care of tearing down the
    :class:`MultihostFixture` object automatically in order to clean up after
    the test run.

    .. note::

        It is preferred that the test case does not use this fixture directly
        but rather access the hosts through dynamically created role fixtures
        that are defined in ``@pytest.mark.topology``.

    :param request: Pytest's ``request`` fixture.
    :type request: pytest.FixtureRequest
    :raises ValueError: If not multihost configuration was given.
    :yield: MultihostFixture
    """

    data: MultihostItemData | None = MultihostItemData.GetData(request.node)
    if data is None:
        nodeid = f"{request.node.parent.nodeid}::{request.node.originalname}"
        raise ValueError(f"{nodeid}: mh fixture requested but no multihost configuration was provided")

    if data.multihost is None:
        raise ValueError("data.multihost must not be None")

    if data.topology_mark is None:
        raise ValueError("data.topology_mark must not be None")

    mh = MultihostFixture(request, data, data.multihost, data.topology_mark)
    try:
        mh._enter()
        mh.log_phase("TEST")
        yield mh
        mh.log_phase("TEST DONE")
    finally:
        mh._exit()
