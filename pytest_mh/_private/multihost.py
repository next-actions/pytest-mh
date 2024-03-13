from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Type, TypeVar

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


class MultihostRole(Generic[HostType]):
    """
    Base role class. Roles are the main interface to the remote hosts that can
    be directly accessed in test cases as fixtures.

    All changes to the remote host that were done through the role object API
    are automatically reverted when a test is finished.
    """

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
        MultihostUtility.SetupUtilityAttributes(self)

    def teardown(self) -> None:
        """
        Teardown all :class:`MultihostUtility` objects
        that are attributes of this class.
        """
        MultihostUtility.TeardownUtilityAttributes(self)

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


class MultihostUtility(Generic[HostType]):
    """
    Base class for utility functions that operate on remote hosts, such as
    writing a file or managing SSSD.

    Instances of :class:`MultihostUtility` can be used in any role class which
    is a subclass of :class:`MultihostRole`. In this case, :func:`setup` and
    :func:`teardown` methods are called automatically when the object is created
    and destroyed to ensure proper setup and clean up on the remote host.
    """

    def __init__(self, host: HostType) -> None:
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

        # Enable first use setup
        disallowed = [
            "artifacts",
            "get_artifacts_list",
            "setup",
            "teardown",
            "setup_when_used",
            "teardown_when_used",
            "GetUtilityAttributes",
            "SetupUtilityAttributes",
            "TeardownUtilityAttributes",
        ]
        for name, method in inspect.getmembers(self, inspect.ismethod):
            if name in disallowed or name.startswith("_") or hasattr(method, "__mh_ignore_call"):
                continue

            setattr(self, name, self.__setup_when_used(method))

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

    def __setup_when_used(self, method):
        @wraps(method)
        def wrapper(*args, **kwargs):
            if not self.used:
                self.used = True
                self.setup_when_used()

            self.used = True
            return method(*args, **kwargs)

        return wrapper

    @staticmethod
    def GetUtilityAttributes(o: object) -> dict[str, MultihostUtility]:
        """
        Get all attributes of the ``o`` that are instance of
        :class:`MultihostUtility`.

        :param o: Any object.
        :type o: object
        :return: Dictionary {attribute name: value}
        :rtype: dict[str, MultihostUtility]
        """
        return dict(inspect.getmembers(o, lambda attr: isinstance(attr, MultihostUtility)))

    @classmethod
    def SetupUtilityAttributes(cls, o: object) -> None:
        """
        Setup all :class:`MultihostUtility` objects attributes of the given
        object.

        :param o: Any object.
        :type o: object
        """
        for util in cls.GetUtilityAttributes(o).values():
            util.setup()

    @classmethod
    def TeardownUtilityAttributes(cls, o: object) -> None:
        """
        Teardown all :class:`MultihostUtility` objects attributes of the given
        object.

        :param o: Any object.
        :type o: object
        """
        errors = []
        for util in cls.GetUtilityAttributes(o).values():
            if util.used:
                try:
                    util.teardown_when_used()
                except Exception as e:
                    errors.append(e)

            try:
                util.teardown()
            except Exception as e:
                errors.append(e)

        if errors:
            raise Exception(errors)

    @classmethod
    def IgnoreCall(cls, method):
        """
        Calling a method decorated with IgnoreCall does not execute neither
        :meth:`setup_when_used` nor :meth:`teardown_when_used`. It does not
        count as "using" the class.
        """
        method.__mh_ignore_call = True
        return method
