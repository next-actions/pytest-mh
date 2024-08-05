"""Client multihost role."""

from __future__ import annotations

import base64
import hashlib
from itertools import count
from typing import Any, Self

import ldap

from ..hosts.ldap import LDAPHost
from ..roles.base import GenericProvider, Group, Sudorule, User

__all__ = [
    "LDAP",
]


class LDAP(GenericProvider[LDAPHost]):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.auto_uid: count[int] = count(10000)
        """Automatically generated uid."""

        self.auto_gid: count[int] = count(10000)
        """Automatically generated gid."""

    def setup(self) -> None:
        """
        Create default organizational units.

        It is not needed to remove them in teardown since the whole LDAP tree
        is restored in topology controller after each test.
        """
        # Note: it would be better to move this to the topology controllers, so
        # this code runs only once. However, it is placed here to demonstrate
        # role setup.
        for name in ["users", "groups", "sudoers"]:
            dn = f"ou={name},{self.host.naming_context}"
            attrs: dict[str, Any] = {"objectClass": "organizationalUnit", "ou": name}

            self.logger.info(f"Creating organizational unit: {dn}")
            self.ldap_add(dn, attrs)

    def user(self, name: str) -> LDAPUser:
        return LDAPUser(self, name)

    def group(self, name: str) -> LDAPGroup:
        return LDAPGroup(self, name)

    def sudorule(self, name: str) -> LDAPSudorule:
        return LDAPSudorule(self, name)

    def hash_password(self, password: str) -> str:
        """
        Compute sha256 hash of a password that can be used as a value.

        :param password: Password to hash.
        :type password: str
        :return: Base64 of sha256 hash digest.
        :rtype: str
        """
        digest = hashlib.sha256(password.encode("utf-8")).digest()
        b64 = base64.b64encode(digest)

        return "{SHA256}" + b64.decode("utf-8")

    def ldap_add(self, dn: str, attrs: dict[str, Any | list[Any] | None]) -> None:
        """
        Add an LDAP entry.

        :param dn: Distinguished name.
        :type dn: str
        :param attrs: Attributes, key is attribute name.
        :type attrs: dict[str, Any | list[Any] | None]
        """
        addlist = []
        for attr, values in attrs.items():
            bytes_values = self.__values_to_bytes(values)

            # Skip if the value is None
            if bytes_values is None:
                continue

            addlist.append((attr, bytes_values))

        self.host.ldap_conn.add_s(dn, addlist)

    def ldap_delete(self, dn: str) -> None:
        """
        Delete LDAP entry.

        :param dn: Distinguished name.
        :type dn: str
        """
        self.host.ldap_conn.delete_s(dn)

    def ldap_modify(
        self,
        dn: str,
        *,
        add: dict[str, Any | list[Any] | None] | None = None,
        replace: dict[str, Any | list[Any] | None] | None = None,
        delete: dict[str, Any | list[Any] | None] | None = None,
    ) -> None:
        """
        Modify LDAP entry.

        :param dn: Distinguished name.
        :type dn: str
        :param add: Attributes to add, defaults to None
        :type add: dict[str, Any | list[Any] | None] | None, optional
        :param replace: Attributes to replace, defaults to None
        :type replace: dict[str, Any | list[Any] | None] | None, optional
        :param delete: Attributes to delete, defaults to None
        :type delete: dict[str, Any | list[Any] | None] | None, optional
        """
        modlist = []

        if add is None:
            add = {}

        if replace is None:
            replace = {}

        if delete is None:
            delete = {}

        for attr, values in add.items():
            modlist.append((ldap.MOD_ADD, attr, self.__values_to_bytes(values)))

        for attr, values in replace.items():
            modlist.append((ldap.MOD_REPLACE, attr, self.__values_to_bytes(values)))

        for attr, values in delete.items():
            modlist.append((ldap.MOD_DELETE, attr, self.__values_to_bytes(values)))

        self.host.ldap_conn.modify_s(dn, modlist)

    def __values_to_bytes(self, values: Any | list[Any]) -> list[bytes] | None:
        """
        Convert values to bytes. Any value is converted to string and then
        encoded into bytes. The input can be either single value or list of
        values or None in which case None is returned.

        :param values: Values.
        :type values: Any | list[Any]
        :return: Values converted to bytes.
        :rtype: list[bytes]
        """
        if values is None:
            return None

        if not isinstance(values, list):
            values = [values]

        return [str(v).encode("utf-8") for v in values]


class LDAPUser(User):
    """
    LDAP user management.
    """

    def __init__(self, role: LDAP, name: str) -> None:
        """
        :param role: LDAP role object.
        :type role: LDAP
        :param name: User name.
        :type name: str
        """
        super().__init__(name)

        self.role: LDAP = role
        self.dn: str = f"cn={name},ou=users,{self.role.host.naming_context}"

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
        Create new LDAP user.

        User and group id is assigned automatically if they are not set. Other
        parameters that are not set are ignored.

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
        self.role.logger.info(f"Creating LDAP user {self.name}")

        # Assign uid and gid automatically if not present to have the same
        # interface as other services.
        if uid is None:
            uid = next(self.role.auto_uid)

        if gid is None:
            gid = uid

        attrs = {
            "objectClass": "posixAccount",
            "cn": self.name,
            "uid": self.name,
            "uidNumber": uid,
            "gidNumber": gid,
            "homeDirectory": f"/home/{self.name}" if home is None else home,
            "userPassword": self.role.hash_password(password) if password is not None else None,
            "gecos": gecos,
            "loginShell": shell,
        }

        self.role.ldap_add(self.dn, attrs)
        return self


class LDAPGroup(Group):
    """
    LDAP group management.
    """

    def __init__(self, role: LDAP, name: str) -> None:
        """
        :param role: LDAP role object.
        :type role: LDAP
        :param name: Group name.
        :type name: str
        """
        super().__init__(name)

        self.role: LDAP = role
        self.dn: str = f"cn={name},ou=groups,{self.role.host.naming_context}"

    def add(
        self,
        *,
        gid: int | None = None,
        members: list[User] | None = None,
        password: str | None = None,
        description: str | None = None,
    ) -> Self:
        """
        Create new LDAP group.

        Group id is assigned automatically if it is not set. Other parameters
        that are not set are ignored.

        :param gid: Group id, defaults to None
        :type gid: int | None, optional
        :param members: List of group members, defaults to None
        :type members: list[User] | None, optional
        :param password: Group password, defaults to None
        :type password: str | None, optional
        :param description: Description, defaults to None
        :type description: str | None, optional
        :return: Self.
        :rtype: Self
        """
        self.role.logger.info(f"Creating LDAP group {self.name}")

        # Assign gid automatically if not present to have the same
        # interface as other services.
        if gid is None:
            gid = next(self.role.auto_gid)

        attrs = {
            "objectClass": "posixGroup",
            "cn": self.name,
            "gidNumber": gid,
            "userPassword": self.role.hash_password(password) if password is not None else None,
            "description": description,
            "memberUid": None,
        }

        self.role.ldap_add(self.dn, attrs)
        if members is not None:
            self.add_members(members)

        return self

    def add_members(self, members: list[User]) -> Self:
        """
        Add multiple group members.

        :param members: Users to add as members.
        :type members: list[User]
        :return: Self.
        :rtype: Self
        """
        attrs: dict[str, Any] = {"memberUid": [x.name for x in members]}

        self.role.logger.info(f"Adding members to LDAP group {self.name}: {attrs['memberUid']}")
        self.role.ldap_modify(self.dn, add=attrs)
        return self

    def remove_members(self, members: list[User]) -> Self:
        """
        Remove multiple group members.

        :param members: Users to remove from this group.
        :type members: list[User]
        :return: Self.
        :rtype: Self
        """
        attrs: dict[str, Any] = {"memberUid": [x.name for x in members]}

        self.role.logger.info(f"Removing members from LDAP group {self.name}: {attrs['memberUid']}")
        self.role.ldap_modify(self.dn, delete=attrs)
        return self


class LDAPSudorule(Sudorule):
    """
    LDAP sudo rule management.
    """

    def __init__(self, role: LDAP, name: str) -> None:
        """
        :param role: LDAP role object.
        :type role: LDAP
        :param name: Sudo rule name.
        :type name: str
        """
        super().__init__(name)

        self.role: LDAP = role
        self.dn: str = f"cn={name},ou=sudoers,{self.role.host.naming_context}"

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
        :type user: User
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

        option = None
        if nopasswd is not None:
            option = "!authenticate" if nopasswd else "authenticate"

        if command is None:
            command = "ALL"

        attrs = {
            "objectClass": "sudoRole",
            "cn": self.name,
            "sudoUser": sudo_user,
            "sudoHost": "ALL",
            "sudoCommand": command,
            "sudoOption": option,
        }

        self.role.ldap_add(self.dn, attrs)
        return self
