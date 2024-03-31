from __future__ import annotations

from abc import ABC, ABCMeta, abstractmethod
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator, Generic, Type, TypeVar

from ..cli import CLIBuilder
from ..ssh import SSHBashProcess, SSHClient, SSHPowerShellProcess, SSHProcess
from .artifacts import (
    MultihostArtifactsCollector,
    MultihostArtifactsMode,
    MultihostArtifactsType,
    MultihostHostArtifacts,
)
from .logging import MultihostHostLogger, MultihostLogger
from .marks import TopologyMark
from .misc import OperationStatus
from .topology import Topology
from .types import MultihostOSFamily
from .utils import validate_configuration

if TYPE_CHECKING:
    from .fixtures import MultihostFixture


class _MultihostRoleMeta(ABCMeta):
    """
    MultihostRole metaclass.

    It finds all MultihostUtility set in the constructor and add it to the
    list of dependencies.

    ABCMeta is not strictly needed for MultihostRole, but it is quite
    possible that inherited classed will require ABC, therefore we have to
    support that out of the box.
    """
    def __call__(cls, *args, **kwargs) -> Any:
        obj = super().__call__(*args, **kwargs)

        obj._mh_utility_dependencies = set()
        for arg in obj.__dict__.values():
            if isinstance(arg, MultihostUtility):
                obj._mh_utility_dependencies.add(arg)

        return obj


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
        if name not in ("MultihostUtility"):
            for attr, value in attrs.items():
                # Do not decorate private stuff
                if attr.startswith("_"):
                    continue

                # Do not decorate stuff from our base classes
                if attr in MultihostUtility.__dict__:
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
        if name in ("MultihostUtility"):
            self._mh_utility_call_setup_when_used = False
            self._mh_utility_call_teardown_when_used = False
            self._mh_utility_used = False
            return super().__init__(name, bases, attrs)

        # we only want to call it if it is defined in inherited classes
        if "setup_when_used" in attrs:
            self._mh_utility_call_setup_when_used = True

        if "teardown_when_used" in attrs:
            self._mh_utility_call_teardown_when_used = True

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


class MultihostHost(Generic[DomainType]):
    """
    Base multihost host class.

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

    def __init__(self, domain: DomainType, confdict: dict[str, Any]):
        """
        :param domain: Multihost domain object.
        :type domain: DomainType
        :param confdict: Host configuration as a dictionary.
        :type confdict: dict[str, Any]
        :param shell: Shell used in SSH connection, defaults to '/usr/bin/bash -c'.
        :type shell: str
        """
        self._op_state: OperationStatus = OperationStatus()
        """Keep state of setup and teardown methods."""

        validate_configuration(
            self.required_fields, confdict, error_fmt='"{key}" property is missing in host configuration'
        )

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

        # SSH
        ssh = confdict.get("ssh", {})

        self.ssh_host: str = ssh.get("host", self.hostname)
        """SSH host (resolvable hostname or IP address), defaults to :attr:`hostname`."""

        self.ssh_port: int = int(ssh.get("port", 22))
        """SSH port, defaults to ``22``."""

        self.ssh_username: str = ssh.get("username", "root")
        """SSH username, defaults to ``root``."""

        self.ssh_password: str = ssh.get("password", "Secret123")
        """SSH password, defaults to ``Secret123``."""

        # Not configurable
        self.shell: Type[SSHProcess] = SSHBashProcess
        """Shell used in SSH session."""

        # Get host operating system information
        os = confdict.get("os", {})

        os_family = str(os.get("family", MultihostOSFamily.Linux.value)).lower()
        try:
            self.os_family: MultihostOSFamily = MultihostOSFamily(os_family)
            """Host operating system os_family."""
        except ValueError:
            raise ValueError(f'Value "{os_family}" is not supported in os_family field of host configuration')

        # Set host shell based on the operating system
        match self.os_family:
            case MultihostOSFamily.Linux:
                self.shell = SSHBashProcess
            case MultihostOSFamily.Windows:
                self.shell = SSHPowerShellProcess
            case _:
                raise ValueError(f"Unknown operating system os_family: {self.os_family}")

        # SSH connection
        self.ssh: SSHClient = SSHClient(
            host=self.ssh_host,
            user=self.ssh_username,
            password=self.ssh_password,
            port=self.ssh_port,
            logger=self.logger,
            shell=self.shell,
        )
        """SSH client."""

        # CLI Builder instance
        self.cli: CLIBuilder = CLIBuilder(self.ssh)
        """Command line builder."""

        # Connect to SSH unless lazy ssh is set
        if not self.mh_domain.mh_config.lazy_ssh:
            self.ssh.connect()

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

    def get_artifacts_list(self, host: MultihostHost, type: MultihostArtifactsType) -> set[str]:
        """
        Return the list of artifacts to collect.

        This just returns :attr:`artifacts`, but it is possible to override this
        method in order to generate additional artifacts that were not created
        by the test, or detect which artifacts were created and update the
        artifacts list.

        :param host: Host where the artifacts are being collected.
        :type host: MultihostHost
        :param type: Type of artifacts that are being collected.
        :type type: MultihostArtifactsType
        :return: List of artifacts to collect.
        :rtype: set[str]
        """
        return self.configured_artifacts.get(type) | self.artifacts.get(type)


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
    _mh_utility_dependencies: set[MultihostUtility]

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
        Setup all :class:`MultihostUtility` objects
        that are attributes of this class.
        """
        mh_utility_setup_dependencies(self)

    def teardown(self) -> None:
        """
        Teardown all :class:`MultihostUtility` objects
        that are attributes of this class.
        """
        mh_utility_teardown_dependencies(self)

    def get_artifacts_list(self, host: MultihostHost, type: MultihostArtifactsType) -> set[str]:
        """
        Return the list of artifacts to collect.

        This just returns :attr:`artifacts`, but it is possible to override this
        method in order to generate additional artifacts that were not created
        by the test, or detect which artifacts were created and update the
        artifacts list.

        :param host: Host where the artifacts are being collected.
        :type host: MultihostHost
        :param type: Type of artifacts that are being collected.
        :type type: MultihostArtifactsType
        :return: List of artifacts to collect.
        :rtype: set[str]
        """
        return self.artifacts

    def ssh(self, user: str, password: str, *, shell=SSHBashProcess) -> SSHClient:
        """
        Open SSH connection to the host as given user.

        :param user: Username.
        :type user: str
        :param password: User password.
        :type password: str
        :param shell: Shell that will run the commands, defaults to SSHBashProcess
        :type shell: str, optional
        :return: SSH client connection.
        :rtype: SSHClient
        """
        return SSHClient(
            self.host.ssh_host,
            user=user,
            password=password,
            port=self.host.ssh_port,
            shell=shell,
            logger=self.logger,
        )


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

    # Following attributes are set by metaclass
    _mh_utility_call_setup_when_used: bool
    _mh_utility_call_teardown_when_used: bool
    _mh_utility_used: bool

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

        self.used: bool = False
        """Indicate if this utility instance was already used or not within current test."""

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

    def setup_when_used(self) -> None:
        """
        Setup the object when it is used for the first time.
        """
        pass

    def teardown_when_used(self) -> None:
        """
        Teardown the object only if it was used.
        """
        pass

    def get_artifacts_list(self, host: MultihostHost, type: MultihostArtifactsType) -> set[str]:
        """
        Return the list of artifacts to collect.

        This just returns :attr:`artifacts`, but it is possible to override this
        method in order to generate additional artifacts that were not created
        by the test, or detect which artifacts were created and update the
        artifacts list.

        :param host: Host where the artifacts are being collected.
        :type host: MultihostHost
        :param host: Host where the artifacts are being collected.
        :type host: MultihostHost
        :param type: Type of artifacts that are being collected.
        :type type: MultihostArtifactsType
        :return: List of artifacts to collect.
        :rtype: set[str]
        """
        return self.artifacts


def mh_utility_used(method):
    """
    Decorator for :class:`MultihostUtility` methods defined in inherited classes.

    Calling decorated method will first invoke :meth:`MultihostUtility.setup_when_called`,
    unless other methods were already called.

    .. note::

        Callables and methods decorated with @property are decorated automatically.

        This decorator can be used to decorate fields declared in __init__ or
        descriptors not handled by pytest-mh.

    :param method: Method to decorate.
    :type method: Callable
    :return: Decorated method.
    :rtype: Callable
    """

    @wraps(method)
    def wrapper(self: MultihostUtility, *args, **kwargs):
        if not self._mh_utility_used:
            self._mh_utility_used = True
            if self._mh_utility_call_setup_when_used:
                self.setup_when_used()
                self._op_state.set_success("setup_when_used")

        return method(self, *args, **kwargs)

    return wrapper


def mh_utility_ignore_use(method):
    """
    Decorator for :class:`MultihostUtility` methods defined in inherited classes.

    Decorated method will not count as "using the class" and therefore it
    will not invoke :meth:`MultihostUtility.setup_when_called`.

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
    util.setup()
    util._op_state.set_success("setup")


def mh_utility_teardown(util: MultihostUtility) -> None:
    """
    Teardown MultihostUtility.

    :param util: Multihost utility object.
    :type util: MultihostUtility
    """
    errors = []
    if util._mh_utility_call_teardown_when_used and util._mh_utility_used:
         if util._op_state.check_success("setup_when_used"):
            try:
                util.teardown_when_used()
            except Exception as e:
                errors.append(e)

    if util._op_state.check_success("setup"):
        try:
            util.teardown()
        except Exception as e:
            errors.append(e)

    if errors:
        raise Exception(errors)


@contextmanager
def mh_utility(util: MultihostUtility) -> Generator[MultihostUtility, None, None]:
    """
    On-demand use of a multihost utility object with a context manager.

    This can be used to automatically setup and teardown a multihost utility
    object that is created on-demand inside a test.

    .. code-block:: python

        with mh_utility(MyUtility(...)) as util:
            util.do_stuff()
    """
    # Mark utility as used so we do not call setup twice (one directly here, and
    # second time via @mh_utility_used decorator). Since the utility is created
    # on demand, we can always call the setup immediately.
    util._mh_utility_used = True
    mh_utility_setup(util)
    try:
        yield util
    finally:
        mh_utility_teardown(util)


def mh_utility_setup_dependencies(obj: MultihostRole) -> None:
    """
    Setup all :class:`MultihostUtility` objects attributes of given object.

    :param obj: Multihost role.
    :type obj: MultihostRole
    """
    for util in obj._mh_utility_dependencies:
        mh_utility_setup(util)


def mh_utility_teardown_dependencies(obj: MultihostRole) -> None:
    """
    Teardown all :class:`MultihostUtility` objects attributes of given object.

    :param obj: Multihost role.
    :type obj: MultihostRole
    """
    errors = []
    for util in obj._mh_utility_dependencies:
        try:
            mh_utility_teardown(util)
        except Exception as e:
            errors.append(e)

    if errors:
        raise Exception(errors)
