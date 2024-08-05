from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Self, TypeVar

from pytest_mh import MultihostRole
from pytest_mh.utils.fs import LinuxFileSystem
from pytest_mh.utils.services import SystemdServices

from ..hosts.base import BaseHost

__all__ = [
    "GenericProvider",
]


HostType = TypeVar("HostType", bound=BaseHost)


class GenericProvider(MultihostRole[HostType], ABC):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.fs: LinuxFileSystem = LinuxFileSystem(self.host)
        """
        File system utilities.
        """

        self.svc: SystemdServices = SystemdServices(self.host)
        """
        Systemd services.
        """

    @abstractmethod
    def user(self, name: str) -> User:
        """
        Get user object.

        :param name: User name.
        :type name: str
        :return: New user object.
        :rtype: User
        """
        pass

    @abstractmethod
    def group(self, name: str) -> Group:
        """
        Get group object.

        :param name: Group name.
        :type name: str
        :return: New group object.
        :rtype: Group
        """
        pass

    @abstractmethod
    def sudorule(self, name: str) -> Sudorule:
        """
        Get sudo rule object.

        :param name: Rule name.
        :type name: str
        :return: New sudo rule object.
        :rtype: Sudorule
        """
        pass


class User(ABC):
    """
    Abstract user type.
    """

    def __init__(self, name: str) -> None:
        """
        :param name: User name.
        :type name: str
        """
        self.name: str = name
        """User name."""

    @abstractmethod
    def add(
        self,
        *,
        uid: int | None = None,
        gid: int | None = None,
        password: str | None = "Secret123",
        home: str | None = None,
        gecos: str | None = None,
        shell: str | None = None,
    ) -> Self:
        """
        Create new user.

        :param uid: User id, defaults to None
        :type uid: int | None, optional
        :param gid: Primary group id, defaults to None
        :type gid: int | None, optional
        :param password: Password, defaults to 'Secret123'
        :type password: str, optional
        :param home: Home directory, defaults to None
        :type home: str | None, optional
        :param gecos: GECOS, defaults to None
        :type gecos: str | None, optional
        :param shell: Login shell, defaults to None
        :type shell: str | None, optional
        :return: Self.
        :rtype: Self
        """
        pass


class Group(ABC):
    """
    Abstract group type.
    """

    def __init__(self, name: str) -> None:
        """
        :param name: Group name.
        :type name: str
        """
        self.name: str = name
        """Group name."""

    @abstractmethod
    def add(
        self,
        *,
        gid: int | None = None,
    ) -> Self:
        """
        Create new local group.

        :param gid: Group id, defaults to None
        :type gid: int | None, optional
        :return: Self.
        :rtype: Self
        """
        pass

    def add_member(self, member: User) -> Self:
        """
        Add group member.

        :param member: User or group to add as a member.
        :type member: User
        :return: Self.
        :rtype: Self
        """
        return self.add_members([member])

    @abstractmethod
    def add_members(self, members: list[User]) -> Self:
        """
        Add multiple group members.

        :param member: List of users to add as members.
        :type member: list[User]
        :return: Self.
        :rtype: Self
        """
        pass

    def remove_member(self, member: User) -> Self:
        """
        Remove group member.

        :param member: User or group to remove from the group.
        :type member: User
        :return: Self.
        :rtype: Self
        """
        return self.remove_members([member])

    @abstractmethod
    def remove_members(self, members: list[User]) -> Self:
        """
        Remove multiple group members.

        :param member: List of users or groups to remove from the group.
        :type member: list[User]
        :return: Self.
        :rtype: Self
        """
        pass


class Sudorule(ABC):
    """
    Abstract sudo rule management.
    """

    def __init__(
        self,
        name: str,
    ) -> None:
        """
        :param name: Sudo rule name.
        :type name: str
        """
        self.name: str = name
        """Sudo rule name."""

    @abstractmethod
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
        :param command: Sudo command, defaults to None
        :type command: str | list[str], optional
        :param nopasswd: If true, no authentication is required (NOPASSWD), defaults to None (no change)
        :type nopasswd: bool | None, optional
        :return: Self.
        :rtype: Self
        """
        pass
