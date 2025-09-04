"""Manage the system hostname using the 'hostname' utility."""

from __future__ import annotations

from collections import deque
from typing import Self

from pytest_mh import MultihostHost, MultihostReentrantUtility
from pytest_mh.conn import ProcessLogLevel

__all__ = ["HostnameUtils"]


class HostnameUtils(MultihostReentrantUtility[MultihostHost]):
    """
    Provides a Python wrapper for the 'hostname' command.

    This is a reentrant utility. When used as a context manager, it will
    automatically save the original hostname on entry and restore it on exit.
    """

    def __init__(self, host: MultihostHost) -> None:
        """
        Initialize the HostnameUtils.

        :param host: Remote host instance.
        :type host: MultihostHost object.
        """
        super().__init__(host)
        self.__states: deque[str] = deque()

    def __enter__(self) -> Self:
        """
        Saves current hostname.

        :return: Self.
        :rtype: Self
        """
        self.logger.info("hostname: backing up current name")
        self.__states.append(self.name)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Reverts hostname changes."""
        _name = self.__states.pop()
        self.logger.info(f"hostname: restoring name to '{_name}'")
        self.name = _name

    @property
    def name(self) -> str:
        """
        Gets hostname.

        :return: Current hostname.
        :rtype: str
        """
        self.logger.info("hostname: getting name")
        result = self.host.conn.exec(["hostname"], log_level=ProcessLogLevel.Error)
        return result.stdout.strip()

    @name.setter
    def name(self, name: str) -> None:
        """
        Sets hostname.

        :param name: The new hostname to set.
        :type name: str
        """
        self.logger.info(f"hostname: setting name to '{name}'")
        self.host.conn.exec(["hostname", name], log_level=ProcessLogLevel.Error)

    @property
    def shortname(self) -> str:
        """
        Gets shortname.

        :return: Short hostname.
        :rtype: str
        """
        self.logger.info("hostname: getting short name")
        result = self.host.conn.exec(["hostname", "-s"], log_level=ProcessLogLevel.Error)
        return result.stdout.strip()

    @property
    def fqdn(self) -> str:
        """
        Gets FQDN.

        :return: FQDN.
        :rtype: str
        """
        self.logger.info("hostname: getting FQDN")
        result = self.host.conn.exec(["hostname", "-f"], log_level=ProcessLogLevel.Error)
        return result.stdout.strip()
