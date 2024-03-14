from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Generator

import pytest

from .artifacts import MultihostArtifactsCollectable
from .data import MultihostItemData
from .logging import MultihostLogger
from .marks import TopologyMark
from .misc import invoke_callback
from .multihost import MultihostConfig, MultihostDomain, MultihostHost, MultihostRole, MultihostUtility
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
        self.topology_controller._invoke_with_args(self.topology_controller.setup)
        self.topology_controller._op_state.set_success("setup")

    def _topology_teardown(self) -> None:
        """
        Run per-test teardown from topology controller.
        """
        if self.topology_controller._op_state.check_success("setup"):
            self.topology_controller._invoke_with_args(self.topology_controller.teardown)

    def _setup(self) -> None:
        """
        Setup multihost. A setup method is called on each host and role
        to initialize the test environment to expected state.
        """
        for item in self.hosts + self.roles:
            item.setup()
            item._op_state.set_success("setup")

    def _collect_artifacts(self) -> None:
        # Create list of collectable objects
        collectable: dict[MultihostHost, list[MultihostArtifactsCollectable]] = {}
        for role in self.roles:
            host_collection = collectable.setdefault(role.host, [role.host, self.topology_controller, role])
            host_collection.extend(MultihostUtility.GetUtilityAttributes(role).values())

        # Collect artifacts, if an error is raised, we will ignore it since
        # teardown is more important
        for host in self.hosts:
            try:
                host.artifacts_collector.collect(
                    "test",
                    path=f"tests/{self.request.node.name}/{host.role}/{host.hostname}",
                    outcome=self.data.outcome,
                    collect_objects=collectable[host],
                )
            except Exception as e:
                self.logger.error(
                    "An error happend when collecting artifacts",
                    extra={
                        "data": {
                            "Error message": str(e),
                        }
                    },
                )

    def _teardown(self) -> None:
        """
        Teardown multihost. The purpose of this method is to revert any changes
        that were made during a test run. It is automatically called when the
        test is finished.
        """
        errors = []
        for item in self.roles + self.hosts:
            if item._op_state.check_success("setup"):
                try:
                    item.teardown()
                except Exception as e:
                    errors.append(e)

        if errors:
            raise Exception(errors)

    def split_log_file(self, name: str) -> None:
        """
        Split current log records into a log file.

        :param name: Log file name.
        :type name: str
        """
        self.logger.split(Path(f"tests/{self.request.node.name}") / name)

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
        self.logger.phase(f"{phase} :: {self.request.node.nodeid}")

    def _enter(self) -> MultihostFixture:
        if self._skip():
            return self

        try:
            self._invoke_phase("SETUP TOPOLOGY", self._topology_setup)
            self._invoke_phase("SETUP TEST", self._setup)
        except Exception:
            self.data.outcome = "error"
            raise
        finally:
            self.split_log_file("setup.log")

        return self

    def _exit(self) -> None:
        if self._skipped:
            return

        errors: list[Exception | None] = []
        errors.append(self._invoke_phase("COLLECT ARTIFACTS", self._collect_artifacts, catch=True))
        errors.append(self._invoke_phase("TEARDOWN TEST", self._teardown, catch=True))
        errors.append(self._invoke_phase("TEARDOWN TOPOLOGY", self._topology_teardown, catch=True))

        self.split_log_file("teardown.log")
        self.logger.flush(self.data.outcome)

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
        if data.outcome == "failed" and data.result is not None:
            mh.logger.error(data.result.longreprtext)

        mh.split_log_file("test.log")
        mh._exit()
