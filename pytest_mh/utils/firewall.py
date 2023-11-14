from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, TypeAlias

from .. import MultihostHost, MultihostUtility
from ..ssh import SSHLog

__all__ = ["LinuxFirewalld"]


ProtocolSpec: TypeAlias = Literal["tcp", "udp"]
"""Firewall protocol specification."""


PortSpec: TypeAlias = int | tuple[int, ProtocolSpec]
"""Firewall port specification."""


ServiceSpec: TypeAlias = str | PortSpec
"""Firewall service specification: service name | port | (port, "tcp" | "udp")."""


class GenericFirewall(ABC, MultihostUtility):
    """
    Configure host firewall.

    All changes are automatically reverted when a test is finished.
    """

    @abstractmethod
    def accept(self, port: PortSpec | list[PortSpec]) -> None:
        """
        Accept incoming traffic on given port.

        .. code-block:: python

            firewall.accept(389)  # missing protocol defaults to "tcp"
            firewall.accept((389, "tcp"))
            firewall.accept([389, 636])

        :param port: Port (integer), (port, protocol) tuple.
        :type port: PortSpec | list[PortSpec]
        """
        pass

    @abstractmethod
    def drop(self, port: PortSpec | list[PortSpec]) -> None:
        """
        Drop incoming traffic on given port.

        .. code-block:: python

            firewall.drop(389)  # missing protocol defaults to "tcp"
            firewall.drop((389, "tcp"))
            firewall.drop([389, 636])

        :param port: Port (integer), (port, protocol) tuple.
        :type port: PortSpec | list[PortSpec]
        """
        pass

    def parse_port_spec(self, spec: PortSpec) -> tuple[int, ProtocolSpec]:
        """
        Parse port specification into (port, protocol) tuple.

        :raises TypeError: When invalid type is given.
        :return: (port, protocol) tuple)
        :rtype: tuple[int, Literal["tcp", "udp"]]
        """
        port: int = 0
        protocol: ProtocolSpec = "tcp"

        if isinstance(spec, int):
            port = spec
            protocol = "tcp"
        elif isinstance(spec, tuple):
            if list(map(type, spec)) == [int, str]:
                port = spec[0]
                protocol = spec[1]
            else:
                raise TypeError(f"Unexpected type: tuple{list(map(type, spec))}")
        else:
            raise TypeError(f"Unexpected type: {type(spec)}")

        if protocol not in ["tcp", "udp"]:
            raise ValueError(f"Unexpected protocol: {protocol}")

        return (port, protocol)


class LinuxFirewalld(GenericFirewall):
    """
    Configure firewall using firewalld.

    All changes are automatically reverted when a test is finished.
    """

    def __init__(self, host: MultihostHost) -> None:
        """
        :param host: Remote host instance.
        :type host: MultihostHost
        """
        super().__init__(host)

        self._priority: int = 30000
        """Next priority for accept/reject/drop rules."""

    def teardown_when_used(self):
        """
        Revert all firewall changes.

        :meta private:
        """
        self.host.ssh.exec(["firewall-cmd", "--reload"])
        super().teardown_when_used()

    def accept(self, port_or_service: ServiceSpec | list[ServiceSpec]) -> None:  # type: ignore[override]
        """
        Accept incoming traffic on given port or service.

        .. code-block:: python

            firewall.accept(389)  # missing protocol defaults to "tcp"
            firewall.accept((389, "tcp"))
            firewall.accept("ldap")
            firewall.accept(["ldap", "ldaps"])

        :param port_or_service: Port (integer), (port, protocol) tuple or service (string).
        :type port_or_service: ServiceSpec | list[ServiceSpec]
        """
        self.__add_action(port_or_service, action="accept")

    def reject(self, port_or_service: ServiceSpec | list[ServiceSpec]) -> None:
        """
        Reject incoming traffic on given port or service.

        .. code-block:: python

            firewall.reject(389)  # missing protocol defaults to "tcp"
            firewall.reject((389, "tcp"))
            firewall.reject("ldap")
            firewall.reject(["ldap", "ldaps"])

        :param port_or_service: Port (integer), (port, protocol) tuple or service (string).
        :type port_or_service: ServiceSpec | list[ServiceSpec]
        """
        self.__add_action(port_or_service, action="reject")

    def drop(self, port_or_service: ServiceSpec | list[ServiceSpec]) -> None:  # type: ignore[override]
        """
        Drop incoming traffic on given port or service.

        .. code-block:: python

            firewall.drop(389)  # missing protocol defaults to "tcp"
            firewall.drop((389, "tcp"))
            firewall.drop("ldap")
            firewall.drop(["ldap", "ldaps"])


        :param port_or_service: Port (integer), (port, protocol) tuple or service (string).
        :type port_or_service: ServiceSpec | list[ServiceSpec]
        """
        self.__add_action(port_or_service, action="drop")

    def add_rich_rule(self, rule: str) -> None:
        """
        Add rich rule.

        :param rule: Firewalld rich rule.
        :type rule: str
        """
        self.logger.info(f'Firewalld: adding rich rule "{rule}"')
        self.host.ssh.exec(["firewall-cmd", "--add-rich-rule", rule], log_level=SSHLog.Error)

    def remove_rich_rule(self, rule: str) -> None:
        """
        Remove rich rule.

        :param rule: Firewalld rich rule.
        :type rule: str
        """
        self.logger.info(f'Firewalld: removing rich rule  "{rule}"')
        self.host.ssh.exec(["firewall-cmd", "--remove-rich-rule", rule], log_level=SSHLog.Error)

    def __add_action(
        self, port_or_service: ServiceSpec | list[ServiceSpec], *, action: Literal["accept", "reject", "drop"]
    ) -> None:
        def __add_port(port: int, protocol: str):
            self.add_rich_rule(f'rule priority="{self._priority}" port port="{port}" protocol="{protocol}" {action}')

        def __add_service(name: str):
            self.add_rich_rule(f'rule priority="{self._priority}" service name="{name}" {action}')

        if not isinstance(port_or_service, list):
            port_or_service = [port_or_service]

        for item in port_or_service:
            if isinstance(item, str):
                __add_service(item)
                continue

            port, protocol = self.parse_port_spec(item)
            __add_port(port, protocol)

        self._priority -= 1


class WindowsFirewall(GenericFirewall):
    """
    Configure Windows firewall.

    All changes are automatically reverted when a test is finished.
    """

    def __init__(self, host: MultihostHost) -> None:
        """
        :param host: Remote host instance.
        :type host: MultihostHost
        """
        super().__init__(host)
        self._changed: bool = False
        """Did we change anything?"""

        self._rules: list[str] = []
        self._backup: str = "C:\\.mh_firewall.bak.wfw"

    def setup_when_used(self):
        """
        Create a backup of current firewall configuration.

        :meta private:
        """
        super().setup_when_used()
        self.logger.info(f"Windows Firewall: creating backup at '{self._backup}'")
        self.host.ssh.run(
            f"Remove-Item {self._backup}; netsh advfirewall export {self._backup}", log_level=SSHLog.Error
        )

    def teardown_when_used(self):
        """
        Revert all firewall changes.

        :meta private:
        """
        self.logger.info(f"Windows Firewall: restoring from '{self._backup}'")
        self.host.ssh.run(f"netsh advfirewall reset; netsh advfirewall import {self._backup}", log_level=SSHLog.Error)
        super().teardown_when_used()

    def accept(self, port: PortSpec | list[PortSpec]) -> None:
        """
        Accept incoming traffic on given port.

        .. code-block:: python

            firewall.accept(389)  # missing protocol defaults to "tcp"
            firewall.accept((389, "tcp"))
            firewall.accept([389, 636])

        :param port: Port (integer), (port, protocol) tuple.
        :type port: PortSpec | list[PortSpec]
        """
        self._add_port_rule(port, action="allow")

    def drop(self, port: PortSpec | list[PortSpec]) -> None:
        """
        Drop incoming traffic on given port.

        .. code-block:: python

            firewall.drop(389)  # missing protocol defaults to "tcp"
            firewall.drop((389, "tcp"))
            firewall.drop([389, 636])

        :param port: Port (integer), (port, protocol) tuple.
        :type port: PortSpec | list[PortSpec]
        """
        self._add_port_rule(port, action="block")

    def _add_port_rule(self, port: PortSpec | list[PortSpec], *, action: Literal["allow", "block"]) -> None:
        if not isinstance(port, list):
            port = [port]

        for item in port:
            port, protocol = self.parse_port_spec(item)

            name = f"mh/{action}/{port}/{protocol}"
            match action:
                case "allow":
                    opposite = f"mh/block/{port}/{protocol}"
                case "block":
                    opposite = f"mh/allow/{port}/{protocol}"
                case _:
                    raise ValueError(f"Unknown action: {action}")

            remove = f"Remove-NetFirewallRule -DisplayName '{opposite}'; " if opposite in self._rules else ""
            add = f"New-NetFirewallRule -DisplayName '{name}' -Action {action} -Protocol {protocol} -LocalPort {port}"

            self.logger.info(f'Windows Firewall: {action} "{port}/{protocol}"')
            self.host.ssh.run(f"{remove}{add}", log_level=SSHLog.Error)
            self._rules.append(name)
