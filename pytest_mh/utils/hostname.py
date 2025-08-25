"""Manage system hostname using the 'hostname' command."""

from __future__ import annotations

from pytest_mh import MultihostHost, MultihostUtility
from pytest_mh.conn import ProcessResult

__all__ = ["HostnameUtils"]


class HostnameUtils(MultihostUtility[MultihostHost]):
    """
    Provides a Python wrapper for the basic 'hostname' command-line utility.
    """

    def __init__(self, host: MultihostHost) -> None:
        """
        Initialize the HostnameUtils.

        :param host: The multihost host instance.
        :type host: MultihostHost
        """
        super().__init__(host)

    @property
    def name(self) -> str:
        """
        Gets the current system hostname by running `hostname`.

        :return: The current hostname as a string.
        :rtype: str
        """
        result = self.host.conn.exec(["hostname"])
        return result.stdout.strip()

    @property
    def short_name(self) -> str:
        """
        Gets the short host name (without the domain) by running `hostname -s`.

        :return: The short hostname as a string.
        :rtype: str
        """
        result = self.host.conn.exec(["hostname", "-s"])
        return result.stdout.strip()

    @property
    def fqdn(self) -> str:
        """
        Gets the Fully Qualified Domain Name (FQDN) by running `hostname -f`.

        :return: The FQDN as a string.
        :rtype: str
        """
        result = self.host.conn.exec(["hostname", "-f"])
        return result.stdout.strip()

    @property
    def domain(self) -> str:
        """
        Gets the system's domain name by running `hostname -d`.

        :return: The domain name as a string.
        :rtype: str
        """
        result = self.host.conn.exec(["hostname", "-d"])
        return result.stdout.strip()

    @property
    def ip_address(self) -> str:
        """
        Gets the primary network address for the hostname by running `hostname -i`.

        :return: The primary IP address as a string.
        :rtype: str
        """
        result = self.host.conn.exec(["hostname", "-i"])
        return result.stdout.strip()

    @property
    def all_ip_addresses(self) -> list[str]:
        """
        Gets all network addresses for the host by running `hostname -I`.

        :return: A list of all IP addresses as strings.
        :rtype: list[str]
        """
        result = self.host.conn.exec(["hostname", "-I"])
        return result.stdout.strip().split()

    def set_name(self, new_name: str) -> ProcessResult:
        """
        Sets the system hostname by running `hostname <new_name>`.
        Note: This typically requires root privileges to execute successfully.

        :param new_name: The new hostname to set for the system.
        :type new_name: str
        :return: The result of the executed command.
        :rtype: ProcessResult
        """
        return self.host.conn.exec(["hostname", new_name])
