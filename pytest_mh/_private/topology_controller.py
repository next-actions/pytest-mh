from __future__ import annotations

from functools import partial, wraps
from types import SimpleNamespace
from typing import Any, Callable, Generic

from .artifacts import MultihostArtifactsType, MultihostTopologyControllerArtifacts
from .logging import MultihostLogger
from .misc import OperationStatus, invoke_callback
from .multihost import ConfigType, MultihostBackupHost, MultihostDomain, MultihostHost
from .topology import Topology, TopologyDomain


class TopologyController(Generic[ConfigType]):
    """
    Topology controller can be associated with a topology via TopologyMark to
    provide additional per-topology hooks such as per-topology setup and
    teardown.

    When inheriting from this class, keep it mind that there is postponed
    initialization of all present properties therefore you can not access them
    inside the constructor. The properties are initialized when a test is
    collected. Override :meth:`init` instead of the constructor if you need to
    access these properties from constructor.

    Each method can take MultihostHost object as parameters as defined in
    topology fixtures.

    .. code-block:: python
        :caption: Example topology controller

        class ExampleController(TopologyController):
            def set_artifacts(self, client: ClientHost) -> None:
                self.artifacts.topology_setup[client] = {"/etc/issue"}

            def skip(self, client: ClientHost) -> str | None:
                result = client.conn.run(
                    ''' # Implement your requirement check here exit 1 ''',
                    raise_on_error=False)
                if result.rc != 0:
                    return "Topology requirements were not met"

                return None

            def topology_setup(self, client: ClientHost):
                # One-time setup, prepare the host for this topology # Changes
                done here are shared for all tests pass

            def topology_teardown(self, client: ClientHost):
                # One-time teardown, this should undo changes from #
                topology_setup pass

            def setup(self, client: ClientHost):
                # Perform per-topology test setup # This is called before
                execution of every test pass

            def teardown(self, client: ClientHost):
                # Perform per-topology test teardown, this should undo changes #
                from setup pass

    .. code-block:: python
        :caption: Example with low-level topology mark

        class ExampleController(TopologyController):
            # Implement methods you are interested in here pass

        @pytest.mark.topology(
            "example", Topology(TopologyDomain("example", client=1)),
            controller=ExampleController(),
            fixtures=dict(client="example.client[0]")
        ) def test_example(client: Client):
            pass

    .. code-block:: python
        :caption: Example with KnownTopology

        class ExampleController(TopologyController):
            # Implement methods you are interested in here pass

        @final @unique class KnownTopology(KnownTopologyBase):
            EXAMPLE = TopologyMark(
                name='example', topology=Topology(TopologyDomain("example",
                client=1)), controller=ExampleController(),
                fixtures=dict(client='example.client[0]'),
            )

        @pytest.mark.topology(KnownTopology.EXAMPLE) def test_example(client:
        Client):
            pass
    """

    def __init__(self) -> None:
        self._op_state: OperationStatus = OperationStatus()
        """Keep state of setup and teardown methods."""

        self.__name: str | None = None
        self.__multihost: ConfigType | None = None
        self.__logger: MultihostLogger | None = None
        self.__topology: Topology | None = None
        self.__ns: SimpleNamespace | None = None
        self.__args: dict[str, MultihostHost | list[MultihostHost]] | None = None
        self.__initialized: bool = False

        self.artifacts: MultihostTopologyControllerArtifacts = MultihostTopologyControllerArtifacts()
        """
        List of artifacts that will be automatically collected at specific
        places. This list can be dynamically extended. Values may contain
        wildcard character.
        """

    def init(
        self,
        name: str,
        multihost: ConfigType,
        logger: MultihostLogger,
        topology: Topology,
        mapping: dict[str, str],
    ):
        """
        Postponed initialization of the topology controller, called by the
        plugin.

        All properties are set and accessible after this method is finished.

        :param name: Topology name.
        :type name: str
        :param multihost: MultihostConfig instance.
        :type multihost: ConfigType
        :param logger: Multihost logger.
        :type logger: MultihostLogger
        :param topology: Topology.
        :type topology: Topology
        :param mapping: Host to fixtures mapping.
        :type mapping: dict[str, str]
        """
        # This is called for each testcase but the controller may be shared with
        # multiple testcases therefore we want to avoid multiple initialization.
        if self.__initialized:
            return

        self.__name = name
        self.__multihost = multihost
        self.__logger = logger
        self.__topology = topology
        self.__ns, self.__args, self.__hosts = self._build_namespace_and_args(multihost.domains, topology, mapping)

        self.__initialized = True

    def _build_namespace_and_args(
        self,
        mh_domains: list[MultihostDomain],
        topology: Topology,
        mapping: dict[str, str],
    ) -> tuple[SimpleNamespace, dict[str, MultihostHost | list[MultihostHost]], list[MultihostHost]]:
        root = SimpleNamespace()
        paths: dict[str, MultihostHost | list[MultihostHost]] = {}
        hosts: set[MultihostHost] = set()

        for mh_domain in mh_domains:
            if mh_domain.id in topology:
                ns, nspaths, nshosts = self._build_domain_namespace_and_paths(topology.get(mh_domain.id), mh_domain)
                setattr(root, mh_domain.id, ns)
                paths.update(**nspaths)
                hosts.update(nshosts)

        args = {}
        for name, path in mapping.items():
            args[name] = paths[path]

        return (root, args, sorted(hosts, key=lambda x: x.hostname))

    def _build_domain_namespace_and_paths(
        self,
        topology_domain: TopologyDomain,
        mh_domain: MultihostDomain,
    ) -> tuple[SimpleNamespace, dict[str, MultihostHost | list[MultihostHost]], set[MultihostHost]]:
        ns = SimpleNamespace()
        paths: dict[str, MultihostHost | list[MultihostHost]] = {}
        domain_hosts: set[MultihostHost] = set()

        for role_name in mh_domain.roles:
            if role_name not in topology_domain:
                continue

            count = topology_domain.get(role_name)
            hosts = [host for host in mh_domain.hosts_by_role(role_name)[:count]]
            domain_hosts.update(hosts)
            setattr(ns, role_name, hosts)

            paths[f"{topology_domain.id}.{role_name}"] = hosts
            for index, host in enumerate(hosts):
                paths[f"{topology_domain.id}.{role_name}[{index}]"] = host

        return (ns, paths, domain_hosts)

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
    def multihost(self) -> ConfigType:
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

    @property
    def hosts(self) -> list[MultihostHost]:
        """
        List of MultihostHost objects available in this topology.

        This property cannot be accessed from the constructor.

        :return: List of MultihostHost objects.
        :rtype: list[MultihostHost]
        """
        if self.__hosts is None:
            raise RuntimeError("TopologyController has not been initialized yet")

        return self.__hosts

    def get_artifacts_list(self, host: MultihostHost, artifacts_type: MultihostArtifactsType) -> set[str]:
        """
        Return the list of artifacts to collect.

        This just returns :attr:`artifacts`, but it is possible to override this
        method in order to generate additional artifacts that were not created
        by the test, or detect which artifacts were created and update the
        artifacts list.

        :param host: Host where the artifacts are being collected.
        :type host: MultihostHost
        :param artifacts_type: Type of artifacts that are being collected.
        :type artifacts_type: MultihostArtifactsType
        :return: List of artifacts to collect.
        :rtype: set[str]
        """
        return self.artifacts.get(host, artifacts_type)

    def set_artifacts(self, *args, **kwargs) -> None:
        """
        Called before :meth:`topology_setup` to set topology artifacts.

        Note that the artifacts can be set in any other method as well. This
        dedicated method is just for your convenience.
        """
        return

    def skip(self, *args, **kwargs) -> str | None:
        """
        Called before a test is executed.

        If a non-None value is returned the test is skipped, using the returned
        value as a skip reason.

        :rtype: str | None
        """
        return None

    def topology_setup(self, *args, **kwargs) -> None:
        """
        Called once before executing the first test of given topology.
        """
        pass

    def topology_teardown(self, *args, **kwargs) -> None:
        """
        Called once after all tests for given topology were run.
        """
        pass

    def setup(self, *args, **kwargs) -> None:
        """
        Called before execution of each test.
        """
        pass

    def teardown(self, *args, **kwargs) -> None:
        """
        Called after execution of each test.
        """
        pass


class BackupTopologyController(TopologyController[ConfigType]):
    """
    Implements automatic backup and restore of all topology hosts that inherit
    from :class:`MultihostBackupHost`.

    The backup of all hosts is taken in :meth:`topology_setup`. It is expected
    that this method is overridden by the user to setup the topology
    environment. In such case, it is possible to call
    ``super().topology_setup(**kwargs)`` at the end of the overridden function
    or omit this call and store the backup in :attr:`backup_data` manually.

    :meth:`teardown` restores the hosts to the backup taken in
    :meth:`topology_setup`. This is done after each test, so each test starts
    with clear topology environment.

    When all tests for this topology are run, :meth:`topology_teardown` is
    called and the hosts are restored to the original state which backup was
    taken in :meth:`MultihostBackupHost.pytest_setup` so the environment is
    fresh for the next topology.

    .. note::

        It is possible to decorate methods, usually the custom implementation of
        :meth:`topology_setup` with :meth:`restore_vanilla_on_error`. This makes
        sure that the hosts are reverted to the original state if any of the
        setup calls fail.

        .. code-block:: python

            @BackupTopologyController.restore_vanilla_on_error
            def topology_setup(self, *kwargs) -> None:
                raise Exception("Hosts are automatically restored now.")
    """

    def __init__(self) -> None:
        super().__init__()

        self.backup_data: dict[MultihostBackupHost, Any | None] = {}
        """
        Backup data. Dictionary with host as a key and backup as a value.
        """

    def restore(self, hosts: dict[MultihostBackupHost, Any | None]) -> None:
        """
        Restore given hosts to their given backup.

        :param hosts: Dictionary (host, backup)
        :type hosts: dict[MultihostBackupHost, Any  |  None]
        :raises ExceptionGroup: If some hosts fail to restore.
        """
        errors = []
        for host, backup_data in hosts.items():
            if not isinstance(host, MultihostBackupHost):
                continue

            try:
                host.restore(backup_data)
            except Exception as e:
                errors.append(e)

        if errors:
            raise ExceptionGroup("Some hosts failed to restore to original state", errors)

    def restore_vanilla(self) -> None:
        """
        Restore to the original host state that is stored in the host object.

        This backup was taken when pytest started and we want to revert to this
        state when this topology is finished.
        """
        restore_data: dict[MultihostBackupHost, Any | None] = {}

        for host in self.hosts:
            if not isinstance(host, MultihostBackupHost):
                continue

            restore_data[host] = host.backup_data

        self.restore(restore_data)

    def topology_setup(self, *args, **kwargs) -> None:
        """
        Take backup of all topology hosts.
        """
        super().topology_setup(**kwargs)

        for host in self.hosts:
            if not isinstance(host, MultihostBackupHost):
                continue

            self.backup_data[host] = host.backup()

    def topology_teardown(self, *args, **kwargs) -> None:
        """
        Remove all topology backups from the hosts and restore the hosts to the
        original state before this topology.
        """
        try:
            for host, backup_data in self.backup_data.items():
                if not isinstance(host, MultihostBackupHost):
                    continue

                host.remove_backup(backup_data)
        except Exception:
            # This is not that important, we can just ignore
            pass

        self.restore_vanilla()

    def teardown(self, *args, **kwargs) -> None:
        """
        Restore the host to the state created by this topology in
        :meth:`topology_setup` after each test is finished.
        """
        self.restore(self.backup_data)

    @staticmethod
    def restore_vanilla_on_error(method):
        """
        Decorator. Restore all hosts to its original state if an exception
        occurs during method execution.

        :param method: Method to decorate.
        :type method: Any setup or teardown callback.
        :return: Decorated method.
        :rtype: Callback
        """

        @wraps(method)
        def wrapper(self: BackupTopologyController, *args, **kwargs):
            try:
                return self._invoke_with_args(partial(method, self))
            except Exception:
                self.restore_vanilla()
                raise

        return wrapper
