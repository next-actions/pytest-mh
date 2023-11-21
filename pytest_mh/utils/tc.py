from __future__ import annotations

from .. import MultihostHost, MultihostUtility
from ..ssh import SSHLog

__all__ = ["LinuxTrafficControl"]


class LinuxTrafficControl(MultihostUtility):
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

    def setup_when_used(self) -> None:
        """
        Setup traffic control configuration.

        :meta private:
        """
        super().setup_when_used()

        # Let's find out the available interfaces
        result = self.host.ssh.run("ip -o address", log_level=SSHLog.Error)
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

        self.host.ssh.run(commands, log_level=SSHLog.Error)

    def teardown_when_used(self) -> None:
        """
        Revert all traffic control changes.

        :meta private:
        """
        tear: str = ""
        for iter in self.__restore_root:
            tear += iter + "\n"
        self.host.ssh.run(tear, log_level=SSHLog.Error)
        super().teardown_when_used()

    def add_delay(self, hostname: str, time: str | int):
        """
        Add delay to the network connection. A maximum of 15 connections can be delayed at a time. It is recommended
        to specify the delay from minimum to maximum to avoid starvation.

        :param hostname: Target hostname.
        :type hostname: str
        :param time: Delay. Units can be specified; if not specified, the default is milliseconds.
        :type time: str | int
        """
        if isinstance(time, int):
            time_unit = f"{time}ms"
        else:
            time_unit = time

        self.logger.info(f"Adding network delay {time_unit} to {hostname}")

        ips = self.host.ssh.run(f"dig +short {hostname}", log_level=SSHLog.Error)
        ip_list = ips.stdout.splitlines()

        commands = "set -e\n"
        for interface in self.__interfaces:
            commands += (
                f"tc qdisc add dev {interface} parent 1:{self.__band} handle {self.__band*10}: netem "
                f"delay {time_unit}\n"
            )
            for ip in ip_list:
                commands += (
                    f"tc filter add dev {interface} protocol ip prio {self.__band} parent 1:0 u32 match ip dst {ip} "
                    f"flowid 1:{self.__band}\n"
                )
                self.__restore_filters[ip] = self.__band

        self.host.ssh.run(commands, log_level=SSHLog.Error)
        self.__band += 1

    def remove_delay(self, hostname: str):
        """
        Remove delay in the network connection.

        :param hostname: Target hostname.
        :type hostname: str
        """
        self.logger.info(f"Removing network delay to {hostname}")

        ips = self.host.ssh.run(f"dig +short {hostname}", log_level=SSHLog.Error)
        ip_list = ips.stdout.splitlines()

        bands: set[int] = set()
        for ip in ip_list:
            if ip in self.__restore_filters:
                bands.add(self.__restore_filters[ip])

        commands = "set -e\n"
        for interface in self.__interfaces:
            for band in bands:
                commands += f"tc filter del dev {interface} prio {band}\n"

            commands += f"tc qdisc del dev {interface} parent 1:{band} handle {band*10}: netem\n"

        self.host.ssh.run(commands, log_level=SSHLog.Error)
