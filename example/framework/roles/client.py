"""Client multihost role."""

from __future__ import annotations

from typing import Self

from pytest_mh.utils.fs import LinuxFileSystem

from ..hosts.client import ClientHost
from ..utils.local_users import LocalGroup, LocalUser, LocalUsersUtils
from ..utils.sudo import SUDOUtils
from .base import GenericProvider, Group, Sudorule, User

__all__ = [
    "Client",
]


class Client(GenericProvider[ClientHost]):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.sudo: SUDOUtils = SUDOUtils(self.host)
        """
        Methods to test sudo.
        """

        self.local_users: LocalUsersUtils = LocalUsersUtils(self.host, self.fs)
        """
        Management of local users and groups.
        """

    def user(self, name: str) -> LocalUser:
        return self.local_users.user(name)

    def group(self, name: str) -> LocalGroup:
        return self.local_users.group(name)

    def sudorule(self, name: str) -> LocalSudorule:
        return LocalSudorule(self.fs, name)


class LocalSudorule(Sudorule):
    """
    Local sudo rule management.
    """

    def __init__(self, fs: LinuxFileSystem, name: str) -> None:
        """
        :param fs: Filesystem utility.
        :type fs: LinuxFileSystem
        :param name: Sudo rule name.
        :type name: str
        """
        super().__init__(name)

        self.fs: LinuxFileSystem = fs

    def add(
        self,
        *,
        user: User | Group,
        command: str | list[str] | None = None,
        nopasswd: bool | None = None,
    ) -> Self:
        """
        Create new sudo rule.

        :param user: Sudo user, defaults to None
        :type user: User | Group
        :param host: Sudo host, defaults to None
        :type host: str | list[str], optional
        :param command: Sudo command, defaults to None
        :type command: str | list[str], optional
        :param nopasswd: If true, no authentication is required (NOPASSWD), defaults to None (no change)
        :type nopasswd: bool | None, optional
        :return: Self.
        :rtype: Self
        """
        sudo_user = user.name
        if isinstance(user, Group):
            sudo_user = f"%{user.name}"

        option = ""
        if nopasswd is not None:
            option = "NOPASSWD: " if nopasswd else ""

        if command is None:
            command = "ALL"

        if not isinstance(command, list):
            command = [command]

        rule = f"{sudo_user} ALL=(root) {option}{', '.join(command)}\n"
        self.fs.append("/etc/sudoers", rule)

        return self
