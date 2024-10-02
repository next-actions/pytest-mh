from __future__ import annotations

from .. import MultihostHost, MultihostRole, MultihostUtility
from ..conn import ProcessLogLevel

__all__ = ["LinuxTrafficControl"]


class LinuxTrafficControl(MultihostUtility[MultihostHost]):
    """
    Perform traffic control operations on remote host.

    All changes are automatically reverted when a test is finished.
    """

    def __init__(self, host: MultihostHost) -> None:
        """
        :param host: Remote host instance.
        :type host: MultihostHost
        """
        super().__init__(host)
        self.__interfaces: set[str] = set()
        self.__restore_root: set[str] = set()
        self.__restore_filters: dict[str, int] = dict()
        self.__band: int = 2

    def setup(self) -> None:
        """
        Setup traffic control configuration.

        :meta private:
        """
        super().setup()

        # Let's find out the available interfaces
        result = self.host.conn.run("ip -o address", log_level=ProcessLogLevel.Error)
        split_result = result.stdout.splitlines()

        for line in split_result:
            interface = line.split(" ")[1]
            if interface != "lo":
                self.__interfaces.add(interface)

        commands = "set -e\n"
        for interface in self.__interfaces:
            commands += (
                f"tc qdisc add dev {interface} root handle 1: prio bands 16 priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n"
            )
            self.__restore_root.add(f"tc qdisc del dev {interface} root")

        self.host.conn.run(commands, log_level=ProcessLogLevel.Error)

    def teardown(self) -> None:
        """
        Revert all traffic control changes.

        :meta private:
        """
        tear: str = ""
        for iter in self.__restore_root:
            tear += iter + "\n"
        self.host.conn.run(tear, log_level=ProcessLogLevel.Error)
        super().teardown()

    def _get_hostname(self, host: str | MultihostHost | MultihostRole) -> str:
        if isinstance(host, str):
            return host

        if isinstance(host, MultihostHost):
            return host.hostname

        if isinstance(host, MultihostRole):
            return host.host.hostname

        raise ValueError(f"Invalid type of host: {type(host)}, expeted str | MultihostHost | MultihostRole")

    def add_delay(self, host: str | MultihostHost | MultihostRole, time: str | int):
        """
        Add delay to the network connection. A maximum of 15 connections can be delayed at a time. It is recommended
        to specify the delay from minimum to maximum to avoid starvation.

        :param host: Target hostname or multihost host or role.
        :type host: str | MultihostHost | MultihostRole
        :param time: Delay. Units can be specified; if not specified, the default is milliseconds.
        :type time: str | int
        """
        hostname = self._get_hostname(host)

        if isinstance(time, int):
            time_unit = f"{time}ms"
        else:
            time_unit = time

        self.logger.info(f"Adding network delay {time_unit} to {hostname}")

        ips = self.host.conn.run(f"dig +short {hostname}", log_level=ProcessLogLevel.Error)
        ip_list = ips.stdout.splitlines()

        commands = "set -e\n"
        for interface in self.__interfaces:
            commands += (
                f"tc qdisc add dev {interface} parent 1:{self.__band} handle {self.__band * 10}: netem "
                f"delay {time_unit}\n"
            )
            for ip in ip_list:
                commands += (
                    f"tc filter add dev {interface} protocol ip prio {self.__band} parent 1:0 u32 match ip dst {ip} "
                    f"flowid 1:{self.__band}\n"
                )
                self.__restore_filters[ip] = self.__band

        self.host.conn.run(commands, log_level=ProcessLogLevel.Error)
        self.__band += 1

    def remove_delay(self, host: str | MultihostHost | MultihostRole):
        """
        Remove delay in the network connection.

        :param host: Target hostname or multihost host or role.
        :type host: str | MultihostHost | MultihostRole
        """
        hostname = self._get_hostname(host)

        self.logger.info(f"Removing network delay to {hostname}")

        ips = self.host.conn.run(f"dig +short {hostname}", log_level=ProcessLogLevel.Error)
        ip_list = ips.stdout.splitlines()

        bands: set[int] = set()
        for ip in ip_list:
            if ip in self.__restore_filters:
                bands.add(self.__restore_filters[ip])

        commands = "set -e\n"
        for interface in self.__interfaces:
            for band in bands:
                commands += f"tc filter del dev {interface} prio {band}\n"

            commands += f"tc qdisc del dev {interface} parent 1:{band} handle {band * 10}: netem\n"

        self.host.conn.run(commands, log_level=ProcessLogLevel.Error)
