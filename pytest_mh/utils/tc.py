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
        self.__restore: set[str] = set()
        self.__band: int = 2

    def setup_when_used(self):
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
            self.__restore.add(f"tc qdisc del dev {interface} root")

        self.host.ssh.run(commands, log_level=SSHLog.Error)

    def teardown_when_used(self):
        """
        Revert all traffic control changes.

        :meta private:
        """
        tear: str = ""
        for iter in self.__restore:
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
        ips = self.host.ssh.run(f"dig +short {hostname}", log_level=SSHLog.Error)
        ip_list = ips.stdout.splitlines()

        if isinstance(time, int):
            time_unit = f"{time}ms"
        else:
            time_unit = time

        commands = "set -e\n"
        for interface in self.__interfaces:
            commands += (
                f"tc qdisc add dev {interface} parent 1:{self.__band} handle {self.__band*10}: netem "
                f"delay {time_unit}\n"
            )
            for ip in ip_list:
                commands += (
                    f"tc filter add dev {interface} protocol ip parent 1:0 u32 match ip dst {ip} "
                    f"flowid 1:{self.__band}\n"
                )

        self.host.ssh.run(commands, log_level=SSHLog.Error)
        self.__band += 1
