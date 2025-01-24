from __future__ import annotations

from abc import ABC, ABCMeta, abstractmethod
from collections import deque
from contextlib import contextmanager
from functools import wraps
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Generator, Generic, Self, Sequence, Type, TypeVar

import pytest

from ..cli import CLIBuilder
from ..conn import (
    Bash,
    Connection,
    Powershell,
    Process,
    ProcessError,
    ProcessInputBuffer,
    ProcessResult,
    ProcessTimeoutError,
    Shell,
)
from ..conn.container import ContainerClient
from ..conn.ssh import SSHClient
from .artifacts import (
    MultihostArtifactsCollector,
    MultihostArtifactsMode,
    MultihostArtifactsType,
    MultihostHostArtifacts,
)
from .errors import TeardownExceptionGroup
from .logging import MultihostHostLogger, MultihostLogger
from .misc import OperationStatus, validate_configuration
from .topology import Topology
from .types import MultihostOSFamily

if TYPE_CHECKING:
    from .fixtures import MultihostFixture
    from .marks import TopologyMark


class _MultihostDependencyMeta(ABCMeta):
    """
    Base meta class that computes on which utilities a class depends.

    It finds all MultihostUtility of given type and add it to the list of
    dependencies.
    """

    def __call__(cls, types: type[MultihostUtility], *args, **kwargs) -> Any:
        obj = super().__call__(*args, **kwargs)

        # Get list of MultihostUtilities used by this object
        obj._mh_utility_dependencies = []
        deps: list[MultihostUtility] = list()
        for arg in obj.__dict__.values():
            if isinstance(arg, types):
                deps.append(arg)

        # Now sort the dependencies, first by class name, then by cross-utility requirements
        deps = sorted(set(deps), key=lambda x: x.__class__.__name__)

        # Now include utilities that do not depend on other utilities
        for util in deps.copy():
            if not util._mh_utility_dependencies:
                obj._mh_utility_dependencies.append(util)
                deps.remove(util)

        # Now sort all utilities that depends on other
        while deps:
            for util in deps.copy():
                if util._mh_utility_dependencies.issubset(obj._mh_utility_dependencies):
                    obj._mh_utility_dependencies.append(util)
                    deps.remove(util)

        return obj


class _MultihostRoleMeta(_MultihostDependencyMeta):
    """
    MultihostRole metaclass.
    """

    def __call__(cls, *args, **kwargs) -> Any:
        return super().__call__(MultihostUtility, *args, **kwargs)


class _MultihostHostMeta(_MultihostDependencyMeta):
    """
    MultihostHost metaclass.
    """

    def __call__(cls, *args, **kwargs) -> Any:
        return super().__call__(MultihostReentrantUtility, *args, **kwargs)


class _MultihostUtilityMeta(ABCMeta):
    """
    MultihostUtility metaclass.

    It takes care of automatic invocation of setup_when_used.

    ABCMeta is not strictly needed for MultihostUtility, but it is quite
    possible that inherited classed will require ABC, therefore we have to
    support that out of the box.
    """

    def __new__(cls, name: str, bases: tuple, attrs: dict[str, Any]) -> _MultihostUtilityMeta:
        # We only decorate stuff from inherited classes
        if name not in ("MultihostUtility", "MultihostReentrantUtility"):
            for attr, value in attrs.items():
                # Do not decorate private stuff
                if attr.startswith("_"):
                    continue

                # Do not decorate stuff from our base classes
                if attr in MultihostUtility.__dict__ or attr in MultihostReentrantUtility.__dict__:
                    continue

                # Do not decorate @staticmethod and @classmethod
                if isinstance(value, (staticmethod, classmethod)):
                    continue

                # Do not decorate stuff marked with @mh_utility_ignore_use
                if hasattr(value, "_mh_utility_ignore_use") and value._mh_utility_ignore_use:
                    continue

                # Decorate supported fields so when used it will automatically
                # invoke setup_when_used()

                # Methods and other callables
                if callable(value):
                    attrs[attr] = mh_utility_used(value)
                    continue

                # @property
                if isinstance(value, property):
                    fget = mh_utility_used(value.fget) if value.fget is not None else None
                    fset = mh_utility_used(value.fset) if value.fset is not None else None
                    fdel = mh_utility_used(value.fdel) if value.fdel is not None else None

                    attrs[attr] = property(fget, fset, fdel, value.__doc__)
                    continue

        return super().__new__(cls, name, bases, attrs)

    def __init__(self, name: str, bases: tuple, attrs: dict[str, Any]) -> None:
        # define special attributes
        if name in ("MultihostUtility", "MultihostReentrantUtility"):
            self._mh_utility_call_setup = False
            self._mh_utility_call_teardown = False
            self._mh_utility_used = False
            return super().__init__(name, bases, attrs)

        # we only want to call setup and teardown if it is defined in inherited classes
        if "setup" in attrs:
            self._mh_utility_call_setup = True

        if "teardown" in attrs:
            self._mh_utility_call_teardown = True

        super().__init__(name, bases, attrs)


class MultihostConfig(ABC):
    """
    Multihost configuration.
    """

    def __init__(
        self,
        confdict: dict[str, Any],
        *,
        logger: MultihostLogger,
        lazy_ssh: bool,
        artifacts_dir: Path,
        artifacts_mode: MultihostArtifactsMode,
        artifacts_compression: bool,
    ) -> None:
        validate_configuration(
            self.required_fields, confdict, error_fmt='"{key}" property is missing in configuration'
        )

        self.confdict: dict[str, Any] = confdict
        """Multihost configuration dictionary given to the constructor."""

        self.config: dict[str, Any] = confdict.get("config", {})
        """Custom configuration."""

        self.logger: MultihostLogger = logger
        """Multihost logger"""

        self.lazy_ssh: bool = lazy_ssh
        """If True, hosts postpone connecting to ssh when the connection is first required"""

        self.artifacts_dir: Path = artifacts_dir
        """Artifacts output directory."""

        self.artifacts_mode: MultihostArtifactsMode = artifacts_mode
        """Artifacts collection mode."""

        self.artifacts_compression: bool = artifacts_compression
        """Store artifacts in compressed archive?"""

        self.domains: list[MultihostDomain] = []
        """Available domains"""

        for domain in confdict["domains"]:
            self.domains.append(self.create_domain(domain))

        self._in_test: bool = False
        """
        Process is currently inside a test.
        """

        self._sigint: bool = False
        """
        SIGINT (CTRL-C) was received.
        """

    @property
    def required_fields(self) -> list[str]:
        """
        Fields that must be set in the host configuration. An error is raised
        if any field is missing.

        The field name may contain a ``.`` to check nested fields.
        """
        return ["domains"]

    @property
    def TopologyMarkClass(self) -> Type[TopologyMark]:
        """
        Class name of the type or subtype of :class:`TopologyMark`.
        """
        from .marks import TopologyMark

        return TopologyMark

    def create_domain(self, domain: dict[str, Any]) -> MultihostDomain:
        """
        Create new multihost domain from dictionary.

        It maps the role name to a Python class using
        :attr:`id_to_domain_class`. If the role is not found in the property, it
        fallbacks to ``*``. If even asterisk is not found, it raises
        ``ValueError``.

        :param domain: Domain in dictionary form.
        :type domain: dict[str, Any]
        :raises ValueError: If domain does not have id or mapping to Python class is not found.
        :return: New multihost domain.
        :rtype: MultihostDomain
        """
        id = domain.get("id", None)
        if id is None:
            raise ValueError("Invalid configuration, domain is missing 'id'")

        cls = self.id_to_domain_class.get(id, self.id_to_domain_class.get("*", None))
        if cls is None:
            raise ValueError(f"Unexpected domain id: {id}")

        return cls(self, domain)

    def topology_hosts(self, topology: Topology) -> list[MultihostHost]:
        """
        Return all hosts required by the topology as list.

        :param topology: Topology.
        :type topology: Multihost topology
        :return: List of MultihostHost.
        :rtype: list[MultihostHost]
        """
        result: list[MultihostHost] = []

        for mh_domain in self.domains:
            if mh_domain.id in topology:
                topology_domain = topology.get(mh_domain.id)
                for role_name in mh_domain.roles:
                    if role_name not in topology_domain:
                        continue

                    count = topology_domain.get(role_name)
                    result.extend(mh_domain.hosts_by_role(role_name)[:count])

        return result

    @property
    @abstractmethod
    def id_to_domain_class(self) -> dict[str, Type[MultihostDomain]]:
        """
        Map domain id to domain class. Asterisk ``*`` can be used as fallback
        value.

        :rtype: Class name.
        """
        pass


ConfigType = TypeVar("ConfigType", bound=MultihostConfig)


class MultihostDomain(ABC, Generic[ConfigType]):
    """
    Multihost domain class.
    """

    def __init__(self, config: ConfigType, confdict: dict[str, Any]) -> None:
        validate_configuration(
            self.required_fields, confdict, error_fmt='"{key}" property is missing in domain configuration'
        )

        self.confdict: dict[str, Any] = confdict
        """Multihost domain configuration dictionary given to the constructor."""

        self.config: dict[str, Any] = confdict.get("config", {})
        """Custom configuration."""

        self.mh_config: ConfigType = config
        """Multihost configuration"""

        self.logger: MultihostLogger = config.logger
        """Multihost logger"""

        self.id: str = confdict["id"]
        """Domain id"""

        self.hosts: list[MultihostHost] = []
        """Available hosts in this domain"""

        for host in confdict["hosts"]:
            self.hosts.append(self.create_host(host))

    @property
    def required_fields(self) -> list[str]:
        """
        Fields that must be set in the domain configuration. An error is raised
        if any field is missing.

        The field name may contain a ``.`` to check nested fields.
        """
        return ["id", "hosts"]

    @property
    def roles(self) -> list[str]:
        """
        All roles available in this domain.

        :return: Role names.
        :rtype: list[str]
        """
        return sorted(set(x.role for x in self.hosts))

    def create_host(self, confdict: dict[str, Any]) -> MultihostHost:
        """
        Create host object from role.

        It maps the role name to a Python class using
        :attr:`role_to_host_class`. If the role is not found in the property, it
        fallbacks to ``*``. If even asterisk is not found, it fallbacks to
        :class:`MultiHost`.

        :param confdict: Host configuration as a dictionary.
        :type confdict: dict[str, Any]
        :raises ValueError: If role property is missing in the host
            configuration.
        :return: Host instance.
        :rtype: MultihostHost
        """
        if not confdict.get("role", None):
            raise ValueError('"role" property is missing in host configuration')

        role = confdict["role"]
        cls = self.role_to_host_class.get(role, self.role_to_host_class.get("*", MultihostHost))

        return cls(self, confdict)

    def create_role(self, mh: MultihostFixture, host: MultihostHost) -> MultihostRole:
        """
        Create role object from given host.

        It maps the role name to a Python class using
        :attr:`role_to_role_class`. If the role is not found in the property, it
        fallbacks to ``*``. If even asterisk is not found, it raises
        ``ValueError``.

        :param mh: Multihost instance.
        :type mh: Multihost
        :param host: Multihost host instance.
        :type host: MultihostHost
        :raises ValueError: If unexpected role name is given.
        :return: Role instance.
        :rtype: MultihostRole
        """
        cls = self.role_to_role_class.get(host.role, self.role_to_role_class.get("*", None))
        if cls is None:
            raise ValueError(f"Unexpected role: {host.role}")

        return cls(mh, host.role, host)

    @property
    @abstractmethod
    def role_to_host_class(self) -> dict[str, Type[MultihostHost]]:
        """
        Map role to host class. Asterisk ``*`` can be used as fallback value.

        :rtype: Class name.
        """
        pass

    @property
    @abstractmethod
    def role_to_role_class(self) -> dict[str, Type[MultihostRole]]:
        """
        Map role to role class. Asterisk ``*`` can be used as fallback value.

        :rtype: Class name.
        """
        pass

    def hosts_by_role(self, role: str) -> list[MultihostHost]:
        """
        Return all hosts of the given role.

        :param role: Role name.
        :type role: str
        :return: List of hosts of given role.
        :rtype: list[MultihostHost]
        """
        return [x for x in self.hosts if x.role == role]


DomainType = TypeVar("DomainType", bound=MultihostDomain)


class MultihostHost(Generic[DomainType], metaclass=_MultihostHostMeta):
    """
    Base multihost host class.

    .. note::

        Host objects may contain MultihostReentrantUtility objects. These
        utilities are automatically setup, entered, exited and teared down.

        It may also contain MultihostUtility objects, but setup and teardown of
        these utilities must be handled manually by in the host or topology
        setup/teardown methods to create the required scope.

    .. code-block:: yaml
        :caption: Example configuration in YAML format

        - hostname: dc.ad.test
          role: ad
          os:
            family: linux
          ssh:
            host: 1.2.3.4
            username: root
            password: Secret123
          config:
            binddn: Administrator@ad.test
            bindpw: vagrant
            client:
              ad_domain: ad.test
              krb5_keytab: /enrollment/ad.keytab
              ldap_krb5_keytab: /enrollment/ad.keytab

    * Required fields: ``hostname``, ``role``
    * Optional fields: ``artifacts``, ``config``, ``os``, ``ssh``
    """

    # Following attributes are set by metaclass
    _mh_utility_dependencies: list[MultihostUtility]

    def __init__(self, domain: DomainType, confdict: dict[str, Any]):
        """
        :param domain: Multihost domain object.
        :type domain: DomainType
        :param confdict: Host configuration as a dictionary.
        :type confdict: dict[str, Any]
        """
        self._op_state: OperationStatus = OperationStatus()
        """Keep state of setup and teardown methods."""

        validate_configuration(
            self.required_fields, confdict, error_fmt='"{key}" property is missing in host configuration'
        )

        self.confdict: dict[str, Any] = confdict
        """Multihost host configuration dictionary given to the constructor."""

        # Required
        self.mh_domain: DomainType = domain
        """Multihost domain."""

        self.role: str = confdict["role"]
        """Host role."""

        self.hostname: str = confdict["hostname"]
        """Host hostname."""

        self.logger: MultihostLogger = self.mh_domain.logger.subclass(
            cls=MultihostHostLogger, suffix=f"host.{self.hostname}", hostname=self.hostname
        )
        """Multihost logger."""

        # Optional
        self.config: dict[str, Any] = confdict.get("config", {})
        """Custom configuration."""

        self.configured_artifacts: MultihostHostArtifacts = MultihostHostArtifacts(confdict.get("artifacts", []))
        """Host artifacts produced during tests, configured by the user."""

        # Get host operating system information
        os = confdict.get("os", {})

        os_family = str(os.get("family", MultihostOSFamily.Linux.value)).lower()
        try:
            self.os_family: MultihostOSFamily = MultihostOSFamily(os_family)
            """Host operating system os_family."""
        except ValueError:
            raise ValueError(f'Value "{os_family}" is not supported in os_family field of host configuration')

        # Not configurable, since we expect specific shells in our code
        self.shell: Shell = Bash()
        """Shell used to run commands over host connection."""

        # Set host shell based on the operating system
        match self.os_family:
            case MultihostOSFamily.Linux:
                pass
            case MultihostOSFamily.Windows:
                self.shell = Powershell()
            case _:
                raise ValueError(f"Unknown operating system os_family: {self.os_family}")

        # Connection to the host
        self.conn: Connection[
            Process[ProcessResult, ProcessInputBuffer, ProcessTimeoutError], ProcessResult[ProcessError]
        ] = self.get_connection()
        """Connection to the host."""

        # CLI Builder instance
        self.cli: CLIBuilder = CLIBuilder(self.shell)
        """Command line builder."""

        self.artifacts: MultihostHostArtifacts = MultihostHostArtifacts()
        """
        List of artifacts that will be automatically collected at specific
        places. This list can be dynamically extended. Values may contain
        wildcard character.
        """

        self.artifacts_collector: MultihostArtifactsCollector = MultihostArtifactsCollector(
            host=self,
            path=self.mh_domain.mh_config.artifacts_dir,
            mode=self.mh_domain.mh_config.artifacts_mode,
            compress=self.mh_domain.mh_config.artifacts_compression,
        )
        """
        Artifacts collector.
        """

    @property
    def required_fields(self) -> list[str]:
        """
        Fields that must be set in the host configuration. An error is raised
        if any field is missing.

        The field name may contain a ``.`` to check nested fields.
        """
        return ["role", "hostname"]

    def pytest_setup(self) -> None:
        """
        Called once before execution of any tests.
        """
        pass

    def pytest_teardown(self) -> None:
        """
        Called once after all tests are finished.
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
        return self.configured_artifacts.get(artifacts_type) | self.artifacts.get(artifacts_type)

    def get_connection(self) -> Connection:
        """
        Get connection object to the host with given shell.

        This creates a connection object using the information from the
        multihost configuration. The caller should not make any assumptions
        about the connection mechanism.

        :return: Generic connection to the host.
        :rtype: Connection
        """
        conn_confdict = self.confdict.get("conn", {})
        conn_type = conn_confdict.setdefault("type", "ssh")

        match conn_type:
            case "ssh":
                return SSHClient.from_confdict(self, conn_confdict)
            case "podman" | "docker":
                return ContainerClient.from_confdict(self, conn_confdict)
            case _:
                raise ValueError(f"Unknown connection type: {conn_type}!")


class MultihostBackupHost(MultihostHost[DomainType], ABC):
    """
    Abstract class implementing automatic backup and restore for a host.

    A backup of the host is created once when pytest starts and the host is
    restored automatically (unless disabled) when a test run is finished.

    If the backup data is stored as :class:`~pathlib.PurePath` or a sequence of
    :class:`~pathlib.PurePath`, the file is automatically removed from the host
    when all tests are finished. Otherwise no action is done -- it is possible
    to overwrite :meth:`remove_backup` to clean up your data if needed.

    It is required to implement :meth:`start`, :meth:`stop`, :meth:`backup` and
    :meth:`restore`. The :meth:`start` method is called in :meth:`pytest_setup`
    unless ``auto_start`` is set to False and the implementation of this method
    may raise ``NotImplementedError`` which will be ignored.

    By default, the host is reverted when each test run is finished. This may
    not always be desirable and can be disabled via ``auto_restore`` parameter
    of the constructor.
    """

    def __init__(self, *args, auto_start: bool = True, auto_restore: bool = True, **kwargs) -> None:
        """
        :param auto_start: Automatically start service before taking the first
            backup.
        :type auto_restore: bool, optional
        :param auto_restore: If True, the host is automatically restored to the
            backup state when a test is finished in :meth:`teardown`, defaults
            to True
        :type auto_restore: bool, optional
        """
        super().__init__(*args, **kwargs)

        self.backup_data: PurePath | Sequence[PurePath] | Any | None = None
        """Backup data of vanilla state of this host."""

        self._backup_auto_start: bool = auto_start
        """
        If True, the host is automatically started prior taking the first
        backup.
        """

        self._backup_auto_restore: bool = auto_restore
        """
        If True, the host is automatically restored to the backup state when a
        test is finished in :meth:`teardown`.
        """

    def pytest_setup(self) -> None:
        """
        Start the services via :meth:`start` and take a backup by calling
        :meth:`backup`.
        """
        # Make sure required services are running
        if self._backup_auto_start:
            try:
                self.start()
            except NotImplementedError:
                pass

        # Create backup of initial state
        self.backup_data = self.backup()

    def pytest_teardown(self) -> None:
        """
        Remove backup files from the host (calls :meth:`remove_backup`).
        """
        self.remove_backup(self.backup_data)

    def teardown(self) -> None:
        """
        Restore the host from the backup by calling :meth:`restore`.
        """
        if self._backup_auto_restore:
            self.restore(self.backup_data)

        super().teardown()

    def remove_backup(self, backup_data: PurePath | Sequence[PurePath] | Any | None) -> None:
        """
        Remove backup data from the host.

        If backup_data is not :class:`~pathlib.PurePath` or a sequence of
        :class:`~pathlib.PurePath`, this will not have any effect. Otherwise,
        the paths are removed from the host.

        :param backup_data: Backup data.
        :type backup_data: PurePath | Sequence[PurePath] | Any | None
        """
        if backup_data is None:
            return

        if isinstance(backup_data, PurePath):
            backup_data = [backup_data]

        if isinstance(backup_data, Sequence):
            only_paths = True
            for item in backup_data:
                if not isinstance(item, PurePath):
                    only_paths = False
                    break

            if only_paths:
                if isinstance(self.conn.shell, Powershell):
                    for item in backup_data:
                        path = str(item)
                        self.conn.exec(["Remove-Item", "-Force", "-Recurse", path])
                else:
                    for item in backup_data:
                        path = str(item)
                        self.conn.exec(["rm", "-fr", path])

    @abstractmethod
    def start(self) -> None:
        """
        Start required services.

        :raises NotImplementedError: If start operation is not supported.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """
        Stop required services.

        :raises NotImplementedError: If stop operation is not supported.
        """
        pass

    @abstractmethod
    def backup(self) -> PurePath | Sequence[PurePath] | Any | None:
        """
        Backup backend data.

        Returns directory or file path where the backup is stored (as
        :class:`~pathlib.PurePath` or sequence of :class:`~pathlib.PurePath`) or
        any Python data relevant for the backup. This data is passed to
        :meth:`restore` which will use this information to restore the host to
        its original state.

        :return: Backup data.
        :rtype: PurePath | Sequence[PurePath] | Any | None
        """
        pass

    @abstractmethod
    def restore(self, backup_data: Any | None) -> None:
        """
        Restore data from the backup.

        :param backup_data: Backup data.
        :type backup_data: PurePath | Sequence[PurePath] | Any | None
        """
        pass


HostType = TypeVar("HostType", bound=MultihostHost)


class MultihostRole(Generic[HostType], metaclass=_MultihostRoleMeta):
    """
    Base role class. Roles are the main interface to the remote hosts that can
    be directly accessed in test cases as fixtures.

    All changes to the remote host that were done through the role object API
    are automatically reverted when a test is finished.

    .. note::

        MultihostRole uses custom metaclass that inherits from ABCMeta.
        Therefore all subclasses can use @abstractmethod any other abc
        decorators without directly inheriting ABCMeta class from ABC.
    """

    # Following attributes are set by metaclass
    _mh_utility_dependencies: list[MultihostUtility]

    def __init__(
        self,
        mh: MultihostFixture,
        role: str,
        host: HostType,
    ) -> None:
        self._op_state: OperationStatus = OperationStatus()
        """Keep state of setup and teardown methods."""

        self.mh: MultihostFixture = mh
        self.role: str = role
        self.host: HostType = host

        self.logger: MultihostLogger = self.host.logger
        """Multihost logger."""

        self.artifacts: set[str] = set()
        """
        List of artifacts that will be automatically collected at specific
        places. This list can be dynamically extended. Values may contain
        wildcard character.
        """

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
        return self.artifacts


class MultihostUtility(Generic[HostType], metaclass=_MultihostUtilityMeta):
    """
    Base class for utility functions that operate on remote hosts, such as
    writing a file or managing SSSD.

    Instances of :class:`MultihostUtility` can be used in any role class which
    is a subclass of :class:`MultihostRole`. In this case, :func:`setup` and
    :func:`teardown` methods are called automatically when the object is created
    and destroyed to ensure proper setup and clean up on the remote host.

    .. note::

        MultihostUtility uses custom metaclass that inherits from ABCMeta.
        Therefore all subclasses can use @abstractmethod any other abc
        decorators without directly inheriting ABCMeta class from ABC.
    """

    # Classvar. This can be overridden by mh_utility_postpone_setup.
    _mh_utility_postpone_setup: bool = False

    # Following attributes are set by metaclass
    _mh_utility_call_setup: bool
    _mh_utility_call_teardown: bool
    _mh_utility_used: bool

    # Set in __new__
    _mh_utility_dependencies: set[MultihostUtility]

    def __new__(cls, *args, **kwargs):
        """
        Find all MultihostUtility objects in the constructor.
        """
        obj = super().__new__(cls)
        obj._mh_utility_dependencies = set()

        for arg in [*args, *kwargs.values()]:
            if isinstance(arg, MultihostUtility):
                obj._mh_utility_dependencies.add(arg)

        return obj

    def __init__(self, host: HostType) -> None:
        self._op_state: OperationStatus = OperationStatus()
        """Keep state of setup and teardown methods."""

        """
        :param host: Remote host instance.
        :type host: HostType
        """
        self.host: HostType = host
        """Multihost host."""

        self.logger: MultihostLogger = self.host.logger
        """Multihost logger."""

        self.artifacts: set[str] = set()
        """
        List of artifacts that will be automatically collected at specific
        places. This list can be dynamically extended. Values may contain
        wildcard character.
        """

    def setup(self) -> None:
        """
        Setup object.
        """
        pass

    def teardown(self) -> None:
        """
        Teardown object.
        """
        pass

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
        return self.artifacts

    def postpone_setup(self) -> Self:
        """
        Postpone setup on this instance of MultihostUtility.

        .. code-block:: python
            :caption: Example usage

            class MyRole(MultihostRole):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)

                    self.firewall: Firewalld = Firewalld(self.host).postpone_setup()

        :return: Self.
        :rtype: Self
        """
        return mh_utility_postpone_setup(self)

    def pytest_report_teststatus(
        self, report: pytest.CollectReport | pytest.TestReport, config: pytest.Config
    ) -> tuple[str, str, str | tuple[str, dict[str, bool]]] | None:
        """
        See pytest built-in hook
        :func:`~_pytest.hookspec.pytest_report_teststatus` for more information.

        .. warning::

            This hook is currently called only if ``report.when == 'call'``,
            that is only after the test is run. This may however change in the
            future, therefore it is recommended to add a test to your code as
            well.

            .. code-block:: python

                class Example(MultihostUtility):
                    def pytest_report_teststatus(self, report, config):
                        if report.when != 'call':
                            return None

                        return ("error", "X", "MYERROR")

        :param report: Pytest report.
        :type report: pytest.CollectReport | pytest.TestReport
        :param config: Pytest config.
        :type config: pytest.Config
        :return: Test status.
        :rtype: tuple[str, str, str | tuple[str, Mapping[str, bool]]] | None
        """
        return None


class MultihostReentrantUtility(MultihostUtility[HostType]):
    """
    Reentrant multihost utility.

    It provides the __enter__ and __exit__ abstract methods that can be called
    multiple times in order to create nested states. The implementation of
    __enter__ should save current state and __exit__ should restore hosts into
    this state.

    The utility can be used as a context manager, leaving the context will
    restore the system to the state during the context enter.
    """

    def __init__(self, host: HostType) -> None:
        super().__init__(host)
        self._mh_exit_stack: deque[tuple[str, bool]] = deque()

    @abstractmethod
    def __enter__(self) -> MultihostReentrantUtility:
        """
        Enter new utility context.

        Typically, a utility saves its state and starts a fresh context.

        :return: Self.
        :rtype: MultihostReentrantUtility
        """
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Leave utility context.

        Typically, a utility restores its state to the previous context and
        reverts all changes done on the host.
        """
        pass


def mh_utility_postpone_setup(cls):
    """
    Class decorator that will postpone calling setup of :class:`MultihostUtility`.

    Decorated class will not invoke setup() before each test immediately but it
    will be postponed to the point when the utility is actually used for the
    first time in the test. This can be used to avoid costly utility setup
    on utilities that are used only sporadically.

    If the utility is not used then setup and teardown method are ignored.

    .. code-block:: python
        :caption: Example

        @mh_utility_postpone_setup
        class ExampleUtility(MultihostUtility):
            def setup(self):
                pass

            def teardown(self):
                pass

    .. seealso::

        There are other decorators that can affect the behavior of postponed
        setup.

            * :func:`mh_utility_used`
            * :func:`mh_utility_ignore_use`

    :param cls: Class to decorate.
    :type cls: type
    :return: Decorated class.
    :rtype: type
    """
    cls._mh_utility_postpone_setup = True
    return cls


def mh_utility_used(method):
    """
    Decorator for :class:`MultihostUtility` methods defined in inherited classes.

    Calling decorated method will first invoke :meth:`MultihostUtility.setup`,
    unless other methods were already called.

    .. note::

        Callables and methods decorated with @property are decorated
        automatically.

        This decorator can be used to decorate fields declared in __init__ or
        descriptors not handled by pytest-mh.

    :param method: Method to decorate.
    :type method: Callable
    :return: Decorated method.
    :rtype: Callable
    """

    @wraps(method)
    def wrapper(self: MultihostUtility, *args, **kwargs):
        if self._mh_utility_postpone_setup and not self._mh_utility_used:
            self._mh_utility_used = True
            mh_utility_setup(self)

            if isinstance(self, MultihostReentrantUtility):
                # Last enter was skipped because the utility was not yet used,
                # we will call it now to save state that we can return in exit.
                where, _ = self._mh_exit_stack.pop()
                mh_utility_enter(self, where)

        return method(self, *args, **kwargs)

    return wrapper


def mh_utility_ignore_use(method):
    """
    Decorator for :class:`MultihostUtility` methods defined in inherited classes.

    Decorated method will not count as "using the class" and therefore it
    will not invoke :meth:`MultihostUtility.setup`.

    .. note::

        This is the opposite of :func:`mh_utility_used`.

    :param method: Method to decorate.
    :type method: Callable
    :return: Decorated method.
    :rtype: Callable
    """
    method._mh_utility_ignore_use = True
    return method


def mh_utility_setup(util: MultihostUtility) -> None:
    """
    Setup MultihostUtility.

    :param util: Multihost utility object.
    :type util: MultihostUtility
    """
    if util._mh_utility_postpone_setup and not util._mh_utility_used:
        return

    if not util._mh_utility_call_setup:
        util._op_state.set_success("setup")
        return

    util.setup()
    util._op_state.set_success("setup")


def mh_utility_teardown(util: MultihostUtility) -> None:
    """
    Teardown MultihostUtility.

    :param util: Multihost utility object.
    :type util: MultihostUtility
    """
    if util._mh_utility_postpone_setup and not util._mh_utility_used:
        return

    if not util._mh_utility_call_teardown:
        return

    if not util._op_state.check_success("setup"):
        return

    util.teardown()


def mh_utility_enter(util: MultihostUtility, where: str) -> None:
    """
    Enter MultihostReentrantUtility.

    This is essentially noop if anything else then MultihostReentrantUtility
    is given, but we keep the type broader to simplify code flow.

    :param util: Multihost utility.
    :type util: MultihostUtility
    :param where: Where do we enter the utility.
    :type where: str
    """
    if not isinstance(util, MultihostReentrantUtility):
        return

    # Do not enter the utility if it was not used yet but postpone setup was requested.
    # However we add a mocked record to indicate that exit should not be called either.
    if util._mh_utility_postpone_setup and not util._mh_utility_used:
        util._mh_exit_stack.append((where, False))
        return

    # We cannot enter/exit if setup was not successful
    if not util._op_state.check_success("setup"):
        raise RuntimeError("Trying to call utility enter without successful setup")

    try:
        util.__enter__()
        util._mh_exit_stack.append((where, True))
    except Exception:
        util._mh_exit_stack.append((where, False))
        raise


def mh_utility_exit(util: MultihostUtility, where: str) -> None:
    """
    Exit MultihostReentrantUtility.

    This is essentially noop if anything else then MultihostReentrantUtility
    is given, but we keep the type broader to simplify code flow.

    :param util: Multihost utility.
    :type util: MultihostUtility
    :param where: Where did we enter the utility.
    :type where: str
    """
    if not isinstance(util, MultihostReentrantUtility):
        return

    # We cannot enter/exit if setup was not successful
    if not util._op_state.check_success("setup"):
        return

    if not util._mh_exit_stack:
        raise IndexError("Calling exit but enter was not called")

    enter_where, enter_result = util._mh_exit_stack.pop()
    if enter_where != where:
        util._mh_exit_stack.append((enter_where, enter_result))
        raise IndexError(f"Calling exit from unexpected place {where}, expected {enter_where}")

    if not enter_result:
        # enter failed, let's not do exit
        return

    util.__exit__(None, None, None)


@contextmanager
def mh_utility(util: MultihostUtility) -> Generator[MultihostUtility, None, None]:
    """
    On-demand use of a multihost utility object with a context manager.

    This can be used to automatically setup and teardown a multihost utility
    object that is created on-demand inside a test.

    .. code-block:: python

        with mh_utility(LinuxFileSystem(role.host)) as fs:
            fs.write("/root/test", "content")
            with fs:
                fs.write("/root/test", "new_content")
                assert fs.read("/root/test") == "new_content"

            assert fs.read("/root/test") == "content"
    """
    # Mark utility as used so we do not call setup twice (one directly here, and
    # second time via @mh_utility_used decorator). Since the utility is created
    # on demand, we can always call the setup immediately.
    util._mh_utility_used = True
    mh_utility_setup(util)
    try:
        mh_utility_enter(util, "mh_utility")
        try:
            yield util
        finally:
            mh_utility_exit(util, "mh_utility")
    finally:
        mh_utility_teardown(util)


def mh_utility_setup_dependencies(
    obj: MultihostRole | MultihostHost,
    types: list[type[MultihostUtility]] = [MultihostUtility, MultihostReentrantUtility],
) -> None:
    """
    Setup all :class:`MultihostUtility` objects attributes of given object.

    :param obj: Multihost role or host object.
    :type obj: MultihostRole | MultihostHost
    :param types: Which MultihostUtility classes should be setup.
    :type types: list[type[MultihostUtility]]
    """
    for util in obj._mh_utility_dependencies:
        if not isinstance(util, tuple(types)):
            continue

        mh_utility_setup(util)
        mh_utility_enter(util, "mh_utility_dependencies")


def mh_utility_teardown_dependencies(
    obj: MultihostRole | MultihostHost,
    types: list[type[MultihostUtility]] = [MultihostUtility, MultihostReentrantUtility],
) -> None:
    """
    Teardown all :class:`MultihostUtility` objects attributes of given object.

    :param obj: Multihost role or host object.
    :type obj: MultihostRole | MultihostHost
    :param types: Which MultihostUtility classes should be setup.
    :type types: list[type[MultihostUtility]]
    """
    errors = []
    for util in reversed(obj._mh_utility_dependencies):
        if not isinstance(util, tuple(types)):
            continue

        try:
            mh_utility_exit(util, "mh_utility_dependencies")
        except Exception as e:
            errors.append(e)
        finally:
            try:
                mh_utility_teardown(util)
            except Exception as e:
                errors.append(e)

    if errors:
        raise TeardownExceptionGroup("Unable to teardown some utilities (util.teardown)", errors)


def mh_utility_enter_dependencies(obj: MultihostRole | MultihostHost, where: str) -> None:
    """
    Setup all :class:`MultihostUtility` objects attributes of given object.

    :param obj: Multihost role or host object.
    :type obj: MultihostRole | MultihostHost
    :param where: Where do we enter the utility.
    :type where: str
    """
    for util in obj._mh_utility_dependencies:
        util._op_state.clear(f"__enter__{where}")

    for util in obj._mh_utility_dependencies:
        util._op_state.set(f"__enter__{where}", "called")
        mh_utility_enter(util, where)


def mh_utility_exit_dependencies(obj: MultihostRole | MultihostHost, where: str) -> None:
    """
    Teardown all :class:`MultihostUtility` objects attributes of given object.

    :param obj: Multihost role or host object.
    :type obj: MultihostRole | MultihostHost
    :param where: Where do we enter the utility.
    :type where: str
    """
    errors = []
    for util in reversed(obj._mh_utility_dependencies):
        if not util._op_state.check(f"__enter__{where}", "called"):
            continue

        try:
            mh_utility_exit(util, where)
        except Exception as e:
            errors.append(e)

        util._op_state.clear(f"__enter__{where}")

    if errors:
        raise TeardownExceptionGroup("Unable to exit some utilities (util.__exit__)", errors)


def mh_utility_pytest_report_teststatus(
    obj: MultihostRole | MultihostHost, report: pytest.CollectReport | pytest.TestReport, config: pytest.Config
) -> tuple[str, str, str | tuple[str, dict[str, bool]]] | None:
    """
    Run :meth:`MultihostUtility.pytest_report_teststatus` on all utilities.

    :param obj: Multihost role or host object.
    :type obj: MultihostRole | MultihostHost
    :param report: Pytest report.
    :type report: pytest.CollectReport | pytest.TestReport
    :param config: Pytest config.
    :type config: pytest.Config
    :return: Test status.
    :rtype: tuple[str, str, str | tuple[str, Mapping[str, bool]]] | None
    """
    for util in obj._mh_utility_dependencies:
        result = util.pytest_report_teststatus(report, config)
        if result is not None:
            return result

    return None
