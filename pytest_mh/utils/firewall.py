from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal, TypeAlias

from .. import MultihostHost, MultihostRole, MultihostUtility
from ..ssh import SSHLog

__all__ = ["Firewalld"]


HostSpec: TypeAlias = str | MultihostHost | MultihostRole
"""Firewall host/hostname specification."""


ProtocolSpec: TypeAlias = Literal["tcp", "udp"]
"""Firewall protocol specification."""


PortSpec: TypeAlias = int | tuple[int, ProtocolSpec]
"""Firewall port specification."""


class Firewall(ABC, MultihostUtility):
    """
    Configure host firewall.

    All changes are automatically reverted when a test is finished.
    """

    @property
    @abstractmethod
    def inbound(self) -> FirewallInboundRules:
        """
        Configure firewall inbound rules.

        :return: Inbound rules manager.
        :rtype: FirewallInboundRules
        """
        pass

    @property
    @abstractmethod
    def outbound(self) -> FirewallOutboundRules:
        """
        Configure firewall outbound rules.

        :return: Outbound rules manager.
        :rtype: FirewalldOutboundRules
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

    def parse_host_spec(self, host: HostSpec) -> str:
        """
        Parse host specification into hostname.

        :raises ValueError: When invalid type is given.
        :return: Hostname.
        :rtype: str
        """
        if isinstance(host, str):
            return host
        elif isinstance(host, MultihostHost):
            return host.hostname
        elif isinstance(host, MultihostRole):
            return host.host.hostname
        else:
            raise ValueError(f"Unexpected type of host: {type(host)}")


class FirewallInboundRules(object):
    """
    Configure firewall inbound rules.

    All changes are automatically reverted when a test is finished.
    """

    @abstractmethod
    def accept_port(self, port: PortSpec | list[PortSpec]) -> None:
        """
        Accept incoming traffic on given port.

        .. code-block:: python

            firewall.inbound.accept_port(389)  # missing protocol defaults to "tcp"
            firewall.inbound.accept_port((389, "tcp"))
            firewall.inbound.accept_port([389, 636])

        :param port: Port (integer), (port, protocol) tuple.
        :type port: PortSpec | list[PortSpec]
        """
        pass

    @abstractmethod
    def drop_port(self, port: PortSpec | list[PortSpec]) -> None:
        """
        Drop incoming traffic on given port.

        .. code-block:: python

            firewall.inbound.drop_port(389)  # missing protocol defaults to "tcp"
            firewall.inbound.drop_port((389, "tcp"))
            firewall.inbound.drop_port([389, 636])

        :param port: Port (integer), (port, protocol) tuple.
        :type port: PortSpec | list[PortSpec]
        """
        pass


class FirewallOutboundRules(object):
    """
    Configure firewall outbound rules.

    All changes are automatically reverted when a test is finished.
    """

    @abstractmethod
    def accept_port(self, port: PortSpec | list[PortSpec]) -> None:
        """
        Accept outgoing traffic on given port.

        .. code-block:: python

            firewall.outbound.accept_port(389)  # missing protocol defaults to "tcp"
            firewall.outbound.accept_port((389, "tcp"))
            firewall.outbound.accept_port([389, 636])

        :param port: Port (integer), (port, protocol) tuple.
        :type port: PortSpec | list[PortSpec]
        """
        pass

    @abstractmethod
    def drop_port(self, port: PortSpec | list[PortSpec]) -> None:
        """
        Drop outgoing traffic on given port.

        .. code-block:: python

            firewall.outbound.drop_port(389)  # missing protocol defaults to "tcp"
            firewall.outbound.drop_port((389, "tcp"))
            firewall.outbound.drop_port([389, 636])

        :param port: Port (integer), (port, protocol) tuple.
        :type port: PortSpec | list[PortSpec]
        """
        pass

    @abstractmethod
    def accept_host(self, host: HostSpec | list[HostSpec]) -> None:
        """
        Accept outgoing traffic to given host.

        The hostname is resolved to IPv4 and IPv6 addresses via DNS and
        an accept rule is created for each available address.

        .. code-block:: python

            firewall.outbound.accept_host("example.com")
            firewall.outbound.accept_host(["example1.com", "example2.com"])
            firewall.outbound.accept_host(multihost_host)
            firewall.outbound.accept_host(multihost_role)

        :param host: Hostname, MultihostHost or MultihostRole object.
        :type host: HostSpec | list[HostSpec]
        """
        pass

    @abstractmethod
    def drop_host(self, host: HostSpec | list[HostSpec]) -> None:
        """
        Drop outgoing traffic to given host.

        The hostname is resolved to IPv4 and IPv6 addresses via DNS and
        an drop rule is created for each available address.

        .. code-block:: python

            firewall.outbound.drop_host("example.com")
            firewall.outbound.drop_host(["example1.com", "example2.com"])
            firewall.outbound.drop_host(multihost_host)
            firewall.outbound.drop_host(multihost_role)

        :param host: Hostname, MultihostHost or MultihostRole object.
        :type host: HostSpec | list[HostSpec]
        """
        pass


class Firewalld(Firewall):
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

        self.__inbound: FirewalldInboundRules = FirewalldInboundRules(self)
        self.__outbound: FirewalldOutboundRules = FirewalldOutboundRules(self)

        self._priority: int = 30000
        """
        Next priority for new firewall rules, when the priority is
        auto-assigned.

        Given the nature of testing, we start with high priority and then
        decrement the value so rules can be easily overwritten (e.g. accept with
        port). E.g. adding a rule "accept port 80" and then "drop port 80" does
        not remove "accept" rule but the "drop" rule takes precedence.
        """

    def teardown_when_used(self) -> None:
        """
        Revert all firewall changes.

        :meta private:
        """
        self.host.ssh.exec(["firewall-cmd", "--reload"])
        super().teardown_when_used()

    @property
    def inbound(self) -> FirewalldInboundRules:
        """
        Configure firewall inbound rules.

        :return: Inbound rules manager.
        :rtype: FirewallInboundRules
        """
        return self.__inbound

    @property
    def outbound(self) -> FirewalldOutboundRules:
        """
        Configure firewall outbound rules.

        :return: Outbound rules manager.
        :rtype: FirewalldOutboundRules
        """
        return self.__outbound

    @property
    def _next_priority(self) -> int:
        """
        Next auto-assigned priority.

        :raises ValueError: _description_
        :return: _description_
        :rtype: int
        """
        priority = self._priority
        if priority < 0:
            raise ValueError("Too many rules defined")

        self._priority -= 1
        return priority

    def add_direct_rule(
        self,
        chain: str,
        args: list[Any],
        *,
        table: str = "filter",
        ip_family: Literal["ipv4", "ipv6", "all"] = "all",
        priority: int | None = None,
    ) -> int:
        """
        Add a new direct rule.

        This methods returns a priority of this rule. You need to use this
        priority if you remove the rule with :meth:`remove_direct_rule`.

        :param chain: iptables chain (e.g. INPUT or OUTPUT).
        :type chain: str
        :param args: iptables arguments
        :type args: list[Any]
        :param table: iptables table, defaults to "filter"
        :type table: str, optional
        :param ip_family: If the rules is added as IPv4, IPv6 rule or both, defaults to ``all``.
        :type ip_family: Literal["ipv4", "ipv6", "all"], optional
        :param priority: Rule priority, defaults to None (= auto-assign next value)
        :type priority: int | None, optional
        :return: Rule priority, to be used for rule removal.
        :rtype: int
        """
        if priority is None:
            priority = self._next_priority

        cmd = [table, chain, priority, *args]

        if ip_family in ["ipv4", "all"]:
            self.logger.info(f'Firewalld: adding IPv4 direct firewall rule: {" ".join([str(x) for x in cmd])}')
            self.host.ssh.exec(["firewall-cmd", "--direct", "--add-rule", "ipv4", *cmd], log_level=SSHLog.Error)

        if ip_family in ["ipv6", "all"]:
            self.logger.info(f'Firewalld: adding IPv6 direct firewall rule: {" ".join([str(x) for x in cmd])}')
            self.host.ssh.exec(["firewall-cmd", "--direct", "--add-rule", "ipv6", *cmd], log_level=SSHLog.Error)

        return priority

    def remove_direct_rule(
        self,
        priority: int,
        chain: str,
        args: list[Any],
        *,
        table: str = "filter",
        ip_family: Literal["ipv4", "ipv6", "all"],
    ) -> None:
        """
        Remove direct rule.

        :param priority: Rule priority.
        :type priority: int
        :param chain: iptables chain (e.g. INPUT or OUTPUT).
        :type chain: str
        :param args: iptables arguments
        :type args: list[Any]
        :param table: iptables table, defaults to "filter"
        :type table: str, optional
        :param ip_family: If the rules is removed from IPv4, IPv6 rules or both, defaults to ``all``.
        :type ip_family: Literal["ipv4", "ipv6", "all"], optional
        """
        cmd = [table, chain, priority, *args]

        if ip_family in ["ipv4", "all"]:
            self.logger.info(f'Firewalld: removing IPv4 direct firewall rule: {" ".join([str(x) for x in cmd])}')
            self.host.ssh.exec(["firewall-cmd", "--direct", "--remove-rule", "ipv4", *cmd], log_level=SSHLog.Error)

        if ip_family in ["ipv6", "all"]:
            self.logger.info(f'Firewalld: removing IPv6 direct firewall rule: {" ".join([str(x) for x in cmd])}')
            self.host.ssh.exec(["firewall-cmd", "--direct", "--remove-rule", "ipv6", *cmd], log_level=SSHLog.Error)

    def add_rich_rule(self, rule: str, priority: int | None = None) -> int:
        """
        Add rich rule.

        The parameter "rule" is the part after "rule priority=X". This part is
        added automatically. That is:

        .. code-block:: console

            $ firewall-cmd --add-rich-rule rule priority={priority} {rule}

        :param rule: Firewalld rich rule.
        :type rule: str
        :param priority: Rule priority, defaults to None (= auto-assign next
            value)
        :type priority: int | None, optional
        :return: Rule priority, to be used for rule removal.
        :rtype: int
        """
        if priority is None:
            priority = self._next_priority

        rule = f"rule priority={priority} {rule}"
        self.logger.info(f'Firewalld: adding rich rule "{rule}"')
        self.host.ssh.exec(["firewall-cmd", "--add-rich-rule", rule], log_level=SSHLog.Error)

        return priority

    def remove_rich_rule(self, priority: int, rule: str) -> None:
        """
        Remove rich rule.

        The parameter "rule" is the part after "rule priority=X". This part is
        added automatically. That is:

        .. code-block:: console

            $ firewall-cmd --remove-rich-rule rule priority="{priority}" {rule}

        :param priority: Rule priority
        :type priority: int
        :param rule: Firewalld rich rule.
        :type rule: str
        """
        rule = f"rule priority={priority} {rule}"
        self.logger.info(f'Firewalld: removing rich rule  "{rule}"')
        self.host.ssh.exec(["firewall-cmd", "--remove-rich-rule", rule], log_level=SSHLog.Error)


class FirewalldInboundRules(FirewallInboundRules):
    """
    Configure firewall inbound rules using firewalld.

    All changes are automatically reverted when a test is finished.
    """

    def __init__(self, firewall: Firewalld) -> None:
        """
        :param firewall: Firewalld controller.
        :type firewall: Firewalld
        """
        super().__init__()

        self.firewall: Firewalld = firewall

    def accept_port(self, port: PortSpec | list[PortSpec]) -> None:
        self.__add_port(port, action="accept")

    def reject_port(self, port: PortSpec | list[PortSpec]) -> None:
        """
        Reject incoming traffic on given port.

        This blocks the communication and also sends icmp-host-unreachable.

        .. code-block:: python

            firewall.inbound.reject_port(389)  # missing protocol defaults to "tcp"
            firewall.inbound.reject_port((389, "tcp"))
            firewall.inbound.reject_port([389, 636])

        :param port: Port (integer), (port, protocol) tuple.
        :type port: PortSpec | list[PortSpec]
        """
        self.__add_port(port, action="reject")

    def drop_port(self, port: PortSpec | list[PortSpec]) -> None:
        self.__add_port(port, action="drop")

    def __add_port(
        self,
        port: PortSpec | list[PortSpec],
        *,
        action: Literal["accept", "reject", "drop"],
    ) -> None:
        def __add_port(port: int, protocol: str):
            self.firewall.add_rich_rule(f'port port="{port}" protocol="{protocol}" {action}')

        def __add_service(name: str):
            self.firewall.add_rich_rule(f'service name="{name}" {action}')

        items = port if isinstance(port, list) else [port]
        for item in items:
            if isinstance(item, str):
                __add_service(item)
                continue

            port, protocol = self.firewall.parse_port_spec(item)
            __add_port(port, protocol)


class FirewalldOutboundRules(FirewallOutboundRules):
    """
    Configure firewall outbound rules using firewalld.

    All changes are automatically reverted when a test is finished.
    """

    def __init__(self, firewall: Firewalld) -> None:
        """
        :param firewall: Firewalld controller.
        :type firewall: Firewalld
        """
        super().__init__()

        self.firewall: Firewalld = firewall

    def accept_port(self, port: PortSpec | list[PortSpec]) -> None:
        self.__add_port(port, action="ACCEPT")

    def reject_port(self, port: PortSpec | list[PortSpec]) -> None:
        self.__add_port(port, action="REJECT")

    def drop_port(self, port: PortSpec | list[PortSpec]) -> None:
        self.__add_port(port, action="DROP")

    def accept_host(self, host: HostSpec | list[HostSpec]) -> None:
        self.__add_host(host, action="ACCEPT")

    def reject_host(self, host: HostSpec | list[HostSpec]) -> None:
        """
        Reject outgoing traffic to given host.

        This blocks the communication and also sends icmp-host-unreachable.

        The hostname is resolved to IPv4 and IPv6 addresses via DNS and
        an drop rule is created for each available address.

        .. code-block:: python

            firewall.outbound.drop_host("example.com")
            firewall.outbound.drop_host(["example1.com", "example2.com"])
            firewall.outbound.drop_host(multihost_host)
            firewall.outbound.drop_host(multihost_role)

        :param host: Hostname, MultihostHost or MultihostRole object.
        :type host: HostSpec | list[HostSpec]
        """
        self.__add_host(host, action="REJECT")

    def drop_host(self, host: HostSpec | list[HostSpec]) -> None:
        self.__add_host(host, action="DROP")

    def __add_port(
        self,
        port: PortSpec | list[PortSpec],
        *,
        action: Literal["ACCEPT", "REJECT", "DROP"],
    ) -> None:
        items = port if isinstance(port, list) else [port]
        for item in items:
            if isinstance(item, str):
                port = int(item)
                protocol = "tcp"
            else:
                port, protocol = self.firewall.parse_port_spec(item)

            self.firewall.add_direct_rule(
                chain="OUTPUT", args=["-p", protocol, "--dport", port, "-j", action], table="filter"
            )

    def __add_host(
        self,
        host: HostSpec | list[HostSpec],
        *,
        action: Literal["ACCEPT", "REJECT", "DROP"],
    ) -> None:
        items = host if isinstance(host, list) else [host]
        for item in items:
            hostname = self.firewall.parse_host_spec(item)
            ipv4s = self.__resolve_hostname(hostname, "A")
            ipv6s = self.__resolve_hostname(hostname, "AAAA")

            self.firewall.logger.info(
                f"Firewalld: adding {action} firewall rule for host {hostname}",
                extra={
                    "data": {
                        "Found IPv4 addresses": ipv4s,
                        "Found IPv6 addresses": ipv6s,
                    }
                },
            )

            for ip in ipv4s:
                self.firewall.add_direct_rule(
                    chain="OUTPUT", args=["--destination", ip, "-j", action], table="filter", ip_family="ipv4"
                )

            for ip in ipv6s:
                self.firewall.add_direct_rule(
                    chain="OUTPUT", args=["--destination", ip, "-j", action], table="filter", ip_family="ipv6"
                )

    def __resolve_hostname(self, hostname: str, type: Literal["A", "AAAA"]) -> list[str]:
        result = self.firewall.host.ssh.exec(["dig", "+short", "-t", type, hostname], log_level=SSHLog.Error)

        return result.stdout_lines


class WindowsFirewall(Firewall):
    """
    Configure Windows Firewall.

    All changes are automatically reverted when a test is finished.
    """

    def __init__(self, host: MultihostHost) -> None:
        """
        :param host: Remote host instance.
        :type host: MultihostHost
        """
        super().__init__(host)

        self.__inbound: WindowsFirewallInboundRules = WindowsFirewallInboundRules(self)
        """Manage inbound rules."""

        self.__outbound: WindowsFirewallOutboundRules = WindowsFirewallOutboundRules(self)
        """Manage outbound rules."""

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

    @property
    def inbound(self) -> WindowsFirewallInboundRules:
        """
        Configure firewall inbound rules.

        :return: Inbound rules manager.
        :rtype: FirewallInboundRules
        """
        return self.__inbound

    @property
    def outbound(self) -> WindowsFirewallOutboundRules:
        """
        Configure firewall outbound rules.

        :return: Outbound rules manager.
        :rtype: FirewalldOutboundRules
        """
        return self.__outbound

    def add_rule(
        self,
        name: str,
        direction: Literal["inbound", "outbound"],
        action: Literal["allow", "block"],
        args: list[Any],
    ) -> str:
        """
        Add firewall rule.

        Final rule name is constructed as ``"mh/{direction}/block/{name}"``.

        :param name: Rule name.
        :type name: str
        :param direction: Direction
        :type direction: Literal["inbound", "outbound"]
        :param action: Action.
        :type action: Literal["allow", "block"]
        :param args: Additional arguments to New-NetFirewallRule command.
        :type args: list[Any]
        :raises ValueError: If invalid action is given.
        :return: Final rule name.
        :rtype: str
        """
        fullname = f"mh/{direction}/{action}/{name}"
        cmd = ["New-NetFirewallRule", "-DisplayName", fullname, "-Direction", direction, "-Action", action, *args]

        match action:
            case "allow":
                opposite = f"mh/{direction}/block/{name}"
            case "block":
                opposite = f"mh/{direction}/allow/{name}"
            case _:
                raise ValueError(f"Unknown action: {action}")

        if opposite in self._rules:
            self.remove_rule(opposite)

        self.logger.info(f'Windows Firewall: adding rule: {" ".join([str(x) for x in cmd])}')
        self.host.ssh.exec(cmd, log_level=SSHLog.Error)
        self._rules.append(fullname)

        return fullname

    def remove_rule(self, name: str) -> None:
        """
        Remove firewall rule.

        :param name: Complete rule name (e.g. ``mh/inbound/block/389``)
        :type name: str
        """
        cmd = ["Remove-NetFirewallRule", "-DisplayName", name]
        self.logger.info(f'Windows Firewall: removing rule: {" ".join([str(x) for x in cmd])}')
        self.host.ssh.exec(cmd, log_level=SSHLog.Error)
        self._rules.remove(name)


class WindowsFirewallInboundRules(FirewallInboundRules):
    """
    Configure firewall inbound rules using Windows Firewall.

    All changes are automatically reverted when a test is finished.
    """

    def __init__(self, firewall: WindowsFirewall) -> None:
        """
        :param firewall: WindowsFirewall controller.
        :type firewall: WindowsFirewall
        """
        super().__init__()

        self.firewall: WindowsFirewall = firewall

    def accept_port(self, port: PortSpec | list[PortSpec]) -> None:
        self.__add_port(port, action="allow")

    def drop_port(self, port: PortSpec | list[PortSpec]) -> None:
        self.__add_port(port, action="block")

    def __add_port(
        self,
        port: PortSpec | list[PortSpec],
        *,
        action: Literal["allow", "block"],
    ) -> None:
        items = port if isinstance(port, list) else [port]
        for item in items:
            port, protocol = self.firewall.parse_port_spec(item)
            self.firewall.add_rule(
                f"{port}/{protocol}", "inbound", action, ["-Protocol", protocol, "-LocalPort", port]
            )


class WindowsFirewallOutboundRules(FirewallOutboundRules):
    """
    Configure firewall outbound rules using Windows Firewall.

    All changes are automatically reverted when a test is finished.
    """

    def __init__(self, firewall: WindowsFirewall) -> None:
        """
        :param firewall: WindowsFirewall controller.
        :type firewall: WindowsFirewall
        """
        super().__init__()

        self.firewall: WindowsFirewall = firewall

    def accept_port(self, port: PortSpec | list[PortSpec]) -> None:
        self.__add_port(port, action="allow")

    def drop_port(self, port: PortSpec | list[PortSpec]) -> None:
        self.__add_port(port, action="block")

    def accept_host(self, host: HostSpec | list[HostSpec]) -> None:
        self.__add_host(host, action="allow")

    def drop_host(self, host: HostSpec | list[HostSpec]) -> None:
        self.__add_host(host, action="block")

    def __add_port(
        self,
        port: PortSpec | list[PortSpec],
        *,
        action: Literal["allow", "block"],
    ) -> None:
        items = port if isinstance(port, list) else [port]
        for item in items:
            port, protocol = self.firewall.parse_port_spec(item)
            self.firewall.add_rule(
                f"{port}/{protocol}", "outbound", action, ["-Protocol", protocol, "-RemotePort", port]
            )

    def __add_host(
        self,
        host: HostSpec | list[HostSpec],
        *,
        action: Literal["allow", "block"],
    ) -> None:
        items = host if isinstance(host, list) else [host]
        for item in items:
            hostname = self.firewall.parse_host_spec(item)
            ipv4s = self.__resolve_hostname(hostname, "A")
            ipv6s = self.__resolve_hostname(hostname, "AAAA")

            self.firewall.logger.info(
                f"Windows Firewall: adding {action} firewall rule for host {hostname}",
                extra={
                    "data": {
                        "Found IPv4 addresses": ipv4s,
                        "Found IPv6 addresses": ipv6s,
                    }
                },
            )

            self.firewall.add_rule(f"{hostname}", "outbound", action, ["-RemoteAddress", ",".join([*ipv4s, *ipv6s])])

    def __resolve_hostname(self, hostname: str, type: Literal["A", "AAAA"]) -> list[str]:
        result = self.firewall.host.ssh.run(
            f"(Resolve-DnsName -Type {type} -Name {hostname}).IpAddress", log_level=SSHLog.Error
        )
        return result.stdout_lines
