"Managing local users and groups."

from __future__ import annotations

from typing import Self

from pytest_mh import MultihostHost, MultihostUtility
from pytest_mh.cli import CLIBuilder, CLIBuilderArgs
from pytest_mh.conn import ProcessLogLevel
from pytest_mh.utils.fs import LinuxFileSystem

from ..roles.base import Group, User

__all__ = [
    "LocalGroup",
    "LocalUser",
    "LocalUsersUtils",
]


class LocalUsersUtils(MultihostUtility[MultihostHost]):
    """
    Management of local users and groups.

    .. note::

        All changes are automatically reverted when a test is finished.
    """

    def __init__(self, host: MultihostHost, fs: LinuxFileSystem) -> None:
        """
        :param host: Remote host instance.
        :type host: MultihostHost
        """
        super().__init__(host)

        self.cli: CLIBuilder = CLIBuilder(host.shell)
        self.fs: LinuxFileSystem = fs
        self._users: list[str] = []
        self._groups: list[str] = []

    def teardown(self) -> None:
        """
        Delete any added user and group.
        """
        cmd = ""

        if self._users:
            cmd += "\n".join([f"userdel '{x}' --force --remove" for x in self._users])
            cmd += "\n"

        if self._groups:
            cmd += "\n".join([f"groupdel '{x}' -f" for x in self._groups])
            cmd += "\n"

        if cmd:
            self.conn.run("set -e\n\n" + cmd)

        super().teardown()

    def user(self, name: str) -> LocalUser:
        """
        Get user object.

        :param name: User name.
        :type name: str
        :return: New user object.
        :rtype: LocalUser
        """
        return LocalUser(self, name)

    def group(self, name: str) -> LocalGroup:
        """
        Get group object.

        :param name: Group name.
        :type name: str
        :return: New group object.
        :rtype: LocalGroup
        """
        return LocalGroup(self, name)


class LocalUser(User):
    """
    Management of local users.
    """

    def __init__(self, util: LocalUsersUtils, name: str) -> None:
        """
        :param util: LocalUsersUtils utility object.
        :type util: LocalUsersUtils
        :param name: User name.
        :type name: str
        """
        super().__init__(name)
        self.util = util

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
        Create new local user.

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
        if home is not None:
            self.util.fs.backup(home)

        args: CLIBuilderArgs = {
            "name": (self.util.cli.option.POSITIONAL, self.name),
            "uid": (self.util.cli.option.VALUE, uid),
            "gid": (self.util.cli.option.VALUE, gid),
            "home": (self.util.cli.option.VALUE, home),
            "gecos": (self.util.cli.option.VALUE, gecos),
            "shell": (self.util.cli.option.VALUE, shell),
        }

        passwd = f" && passwd --stdin '{self.name}'" if password else ""
        self.util.logger.info(f'Creating local user "{self.name}"')
        self.util.conn.run(
            self.util.cli.command("useradd", args) + passwd, input=password, log_level=ProcessLogLevel.Error
        )

        self.util._users.append(self.name)
        return self


class LocalGroup(Group):
    """
    Management of local groups.
    """

    def __init__(self, util: LocalUsersUtils, name: str) -> None:
        """
        :param util: LocalUsersUtils utility object.
        :type util: LocalUsersUtils
        :param name: Group name.
        :type name: str
        """
        super().__init__(name)
        self.util = util

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
        :rtype: elf
        """
        args: CLIBuilderArgs = {
            "name": (self.util.cli.option.POSITIONAL, self.name),
            "gid": (self.util.cli.option.VALUE, gid),
        }

        self.util.logger.info(f'Creating local group "{self.name}"')
        self.util.conn.run(self.util.cli.command("groupadd", args), log_level=ProcessLogLevel.Silent)
        self.util._groups.append(self.name)

        return self

    def add_members(self, members: list[User]) -> Self:
        """
        Add multiple group members.

        :param member: List of users or groups to add as members.
        :type member: list[User]
        :return: Self.
        :rtype: Self
        """
        self.util.logger.info(f'Adding members to group "{self.name}"')

        if not members:
            return self

        cmd = "\n".join([f"groupmems --group '{self.name}' --add '{x.name}'" for x in members])
        self.util.conn.run("set -ex\n" + cmd, log_level=ProcessLogLevel.Error)

        return self

    def remove_members(self, members: list[User]) -> Self:
        """
        Remove multiple group members.

        :param member: List of users or groups to remove from the group.
        :type member: list[User]
        :return: Self.
        :rtype: Self
        """
        self.util.logger.info(f'Removing members from group "{self.name}"')

        if not members:
            return self

        cmd = "\n".join([f"groupmems --group '{self.name}' --delete '{x.name}'" for x in members])
        self.util.conn.run("set -ex\n" + cmd, log_level=ProcessLogLevel.Error)

        return self
