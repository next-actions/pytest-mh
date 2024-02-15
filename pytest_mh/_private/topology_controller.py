from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable

from .logging import MultihostLogger
from .misc import OperationStatus, invoke_callback
from .topology import Topology, TopologyDomain

if TYPE_CHECKING:
    from .multihost import MultihostConfig, MultihostDomain, MultihostHost


class TopologyController(object):
    """
    Topology controller can be associated with a topology via TopologyMark
    to provide additional per-topology hooks such as per-topology setup
    and teardown.

    When inheriting from this class, keep it mind that there is postpone
    initialization of all present properties therefore you can not access
    them inside the constructor. The properties are initialized a test is
    collected.

    Each method can take MultihostHost object as parameters as defined in
    topology fixtures.

    .. code-block:: python
        :caption: Example topology controller

        class ExampleController(TopologyController):
            def skip(self, client: ClientHost) -> str | None:
                result = client.ssh.run(
                    '''
                    # Implement your requirement check here
                    exit 1
                    ''', raise_on_error=False)
                if result.rc != 0:
                    return "Topology requirements were not met"

                return None

            def topology_setup(self, client: ClientHost):
                # One-time setup, prepare the host for this topology
                # Changes done here are shared for all tests
                pass

            def topology_teardown(self, client: ClientHost):
                # One-time teardown, this should undo changes from
                # topology_setup
                pass

            def setup(self, client: ClientHost):
                # Perform per-topology test setup
                # This is called before execution of every test
                pass

            def teardown(self, client: ClientHost):
                # Perform per-topology test teardown, this should undo changes
                # from setup
                pass

    .. code-block:: python
        :caption: Example with low-level topology mark

        class ExampleController(TopologyController):
            # Implement methods you are interested in here
            pass

        @pytest.mark.topology(
            "example", Topology(TopologyDomain("example", client=1)),
            controller=ExampleController(),
            fixtures=dict(client="example.client[0]")
        )
        def test_example(client: Client):
            pass

    .. code-block:: python
        :caption: Example with KnownTopology

        class ExampleController(TopologyController):
            # Implement methods you are interested in here
            pass

        @final
        @unique
        class KnownTopology(KnownTopologyBase):
            EXAMPLE = TopologyMark(
                name='example',
                topology=Topology(TopologyDomain("example", client=1)),
                controller=ExampleController(),
                fixtures=dict(client='example.client[0]'),
            )

        @pytest.mark.topology(KnownTopology.EXAMPLE)
        def test_example(client: Client):
            pass
    """

    def __init__(self) -> None:
        self._op_state: OperationStatus = OperationStatus()
        """Keep state of setup and teardown methods."""

        self.__name: str | None = None
        self.__multihost: MultihostConfig | None = None
        self.__logger: MultihostLogger | None = None
        self.__topology: Topology | None = None
        self.__ns: SimpleNamespace | None = None
        self.__args: dict[str, MultihostHost | list[MultihostHost]] | None = None
        self.__initialized: bool = False

    def _init(
        self,
        name: str,
        multihost: MultihostConfig,
        logger: MultihostLogger,
        topology: Topology,
        mapping: dict[str, str],
    ):
        # This is called for each testcase but the controller may be shared with
        # multiple testcases therefore we want to avoid multiple initialization.
        if self.__initialized:
            return

        self.__name = name
        self.__multihost = multihost
        self.__logger = logger
        self.__topology = topology
        self.__ns, self.__args = self._build_namespace_and_args(multihost.domains, topology, mapping)

        self.__initialized = True

    def _build_namespace_and_args(
        self,
        mh_domains: list[MultihostDomain],
        topology: Topology,
        mapping: dict[str, str],
    ) -> tuple[SimpleNamespace, dict[str, MultihostHost | list[MultihostHost]]]:
        root = SimpleNamespace()
        paths: dict[str, MultihostHost | list[MultihostHost]] = {}

        for mh_domain in mh_domains:
            if mh_domain.id in topology:
                ns, nspaths = self._build_domain_namespace_and_paths(topology.get(mh_domain.id), mh_domain)
                setattr(root, mh_domain.id, ns)
                paths.update(**nspaths)

        args = {}
        for name, path in mapping.items():
            args[name] = paths[path]

        return (root, args)

    def _build_domain_namespace_and_paths(
        self,
        topology_domain: TopologyDomain,
        mh_domain: MultihostDomain,
    ) -> tuple[SimpleNamespace, dict[str, MultihostHost | list[MultihostHost]]]:
        ns = SimpleNamespace()
        paths: dict[str, MultihostHost | list[MultihostHost]] = {}

        for role_name in mh_domain.roles:
            if role_name not in topology_domain:
                continue

            count = topology_domain.get(role_name)
            hosts = [host for host in mh_domain.hosts_by_role(role_name)[:count]]
            setattr(ns, role_name, hosts)

            paths[f"{topology_domain.id}.{role_name}"] = hosts
            for index, host in enumerate(hosts):
                paths[f"{topology_domain.id}.{role_name}[{index}]"] = host

        return (ns, paths)

    def _invoke_with_args(self, cb: Callable) -> Any:
        if self.__args is None:
            raise RuntimeError("TopologyController has not been initialized yet")

        return invoke_callback(cb, **self.__args)

    @property
    def name(self) -> str:
        """
        Topology name.

        This property cannot be accessed from the constructor.

        :return: Topology name.
        :rtype: str
        """
        if self.__name is None:
            raise RuntimeError("TopologyController has not been initialized yet")

        return self.__name

    @property
    def topology(self) -> Topology:
        """
        Multihost topology.

        This property cannot be accessed from the constructor.

        :return: Topology.
        :rtype: Topology
        """
        if self.__topology is None:
            raise RuntimeError("TopologyController has not been initialized yet")

        return self.__topology

    @property
    def multihost(self) -> MultihostConfig:
        """
        Multihost configuration.

        This property cannot be accessed from the constructor.

        :return: Multihost configuration.
        :rtype: MultihostConfig
        """
        if self.__multihost is None:
            raise RuntimeError("TopologyController has not been initialized yet")

        return self.__multihost

    @property
    def logger(self) -> MultihostLogger:
        """
        Multihost logger.

        This property cannot be accessed from the constructor.

        :return: Multihost logger.
        :rtype: MultihostLogger
        """
        if self.__logger is None:
            raise RuntimeError("TopologyController has not been initialized yet")

        return self.__logger

    @property
    def ns(self) -> SimpleNamespace:
        """
        Namespace of MultihostHost objects accessible by domain id and roles names.

        This property cannot be accessed from the constructor.

        :return: Namespace.
        :rtype: SimpleNamespace
        """
        if self.__ns is None:
            raise RuntimeError("TopologyController has not been initialized yet")

        return self.__ns

    def skip(self) -> str | None:
        """
        Called before a test is executed.

        If a non-None value is returned the test is skipped, using the returned
        value as a skip reason.

        :rtype: str | None
        """
        return None

    def topology_setup(self) -> None:
        """
        Called once before executing the first test of given topology.
        """
        pass

    def topology_teardown(self) -> None:
        """
        Called once after all tests for given topology were run.
        """
        pass

    def setup(self) -> None:
        """
        Called before execution of each test.
        """
        pass

    def teardown(self) -> None:
        """
        Called after execution of each test.
        """
        pass
