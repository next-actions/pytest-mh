from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from base64 import b64decode
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Type, TypeVar

from ..cli import CLIBuilder
from ..ssh import SSHBashProcess, SSHClient, SSHLog, SSHPowerShellProcess, SSHProcess
from .logging import MultihostLogger
from .marks import TopologyMark
from .utils import validate_configuration

if TYPE_CHECKING:
    from .fixtures import MultihostFixture


class MultihostConfig(ABC):
    """
    Multihost configuration.
    """

    def __init__(self, confdict: dict[str, Any], *, logger: MultihostLogger, lazy_ssh: bool = False) -> None:
        validate_configuration(
            self.required_fields, confdict, error_fmt='"{key}" property is missing in configuration'
        )

        self.logger: MultihostLogger = logger
        """Multihost logger"""

        self.lazy_ssh: bool = lazy_ssh
        """If True, hosts postpone connecting to ssh when the connection is first required"""

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

        self.config: ConfigType = config
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


class MultihostHostOSFamily(Enum):
    """
    Host operating system family.
    """

    Linux = "linux"
    Windows = "windows"


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
        validate_configuration(
            self.required_fields, confdict, error_fmt='"{key}" property is missing in host configuration'
        )

        # Required
        self.domain: DomainType = domain
        """Multihost domain."""

        self.logger: MultihostLogger = domain.logger
        """Multihost logger."""

        self.role: str = confdict["role"]
        """Host role."""

        self.hostname: str = confdict["hostname"]
        """Host hostname."""

        # Optional
        self.config: dict[str, Any] = confdict.get("config", {})
        """Custom configuration."""

        self.artifacts: list[str] = confdict.get("artifacts", [])
        """Host artifacts produced during tests."""

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

        os_family = str(os.get("family", MultihostHostOSFamily.Linux.value)).lower()
        try:
            self.os_family: MultihostHostOSFamily = MultihostHostOSFamily(os_family)
            """Host operating system os_family."""
        except ValueError:
            raise ValueError(f'Value "{os_family}" is not supported in os_family field of host configuration')

        # Set host shell based on the operating system
        match self.os_family:
            case MultihostHostOSFamily.Linux:
                self.shell = SSHBashProcess
            case MultihostHostOSFamily.Windows:
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
        if not self.domain.config.lazy_ssh:
            self.ssh.connect()

    @property
    def required_fields(self) -> list[str]:
        """
        Fields that must be set in the host configuration. An error is raised
        if any field is missing.

        The field name may contain a ``.`` to check nested fields.
        """
        return ["role", "hostname"]

    def collect_artifacts(self, dest: str) -> None:
        """
        Collect test artifacts that were requested by the multihost configuration.

        :param dest: Destination directory, where the artifacts will be stored.
        :type dest: str
        """
        if not self.artifacts:
            return

        # Create output directory
        Path(dest).mkdir(parents=True, exist_ok=True)

        # Fetch artifacts
        match self.os_family:
            case MultihostHostOSFamily.Linux:
                command = f"""
                    tmp=`mktemp /tmp/mh.host.artifacts.XXXXXXXXX`
                    tar -czvf "$tmp" {' '.join([f'$(compgen -G "{x}")' for x in self.artifacts])} &> /dev/null
                    base64 "$tmp"
                    rm -f "$tmp" &> /dev/null
                """
                ext = "tgz"
            case MultihostHostOSFamily.Windows:
                raise NotImplementedError("Artifacts are not supported on Windows machine")
            case _:
                raise ValueError(f"Unknown operating system: {self.os_family}")

        result = self.ssh.run(command, log_level=SSHLog.Error)

        # Store artifacts in single archive
        with open(f"{dest}/{self.role}_{self.hostname}.{ext}", "wb") as f:
            f.write(b64decode(result.stdout))

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
        self.mh: MultihostFixture = mh
        self.role: str = role
        self.host: HostType = host

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
            logger=self.mh.logger,
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

        # Enable first use setup
        disallowed = [
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

    def __setup_when_used(self, method):
        @wraps(method)
        def wrapper(*args, **kwargs):
            if not self.used:
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
