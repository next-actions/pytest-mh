"""LDAP multihost host."""

from __future__ import annotations

from typing import Any

import ldap
import ldap.modlist
from ldap.ldapobject import ReconnectLDAPObject

from .base import BaseHost

__all__ = [
    "LDAPHost",
]


class LDAPHost(BaseHost):
    """
    LDAP Host.

    Provides backup and restore of an 389-ds server. It also maintains
    a connection to the server via :attr:`ldap_conn`.

    Expectations:

    * 389-ds-server is installed
    * sudo schema is installed
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Add custom configuration options
        self.svc_name = self.config.get("service_name", "dirsrv@localhost.service")
        """Dirsrv service name ``config.service_name``, defaults to ``dirsrv@localhost.service``"""

        self.binddn: str = self.config.get("binddn", "cn=Directory Manager")
        """Bind DN ``config.binddn``, defaults to ``cn=Directory Manager``"""

        self.bindpw: str = self.config.get("bindpw", "Secret123")
        """Bind password ``config.bindpw``, defaults to ``Secret123``"""

        # Lazy properties.
        self.__ldap_conn: ReconnectLDAPObject | None = None
        self.__naming_context: str | None = None

    @property
    def ldap_conn(self) -> ReconnectLDAPObject:
        """
        LDAP connection (``python-ldap`` library).

        :rtype: ReconnectLDAPObject
        """
        if not self.__ldap_conn:
            # Use host from SSH if possible, otherwise fallback to hostname
            host = getattr(self.conn, "host", self.hostname)

            # Setup connection
            newconn = ReconnectLDAPObject(f"ldap://{host}")
            newconn.protocol_version = ldap.VERSION3
            newconn.set_option(ldap.OPT_REFERRALS, 0)

            # Setup TLS
            newconn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
            newconn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
            newconn.start_tls_s()

            # Authenticate
            newconn.simple_bind_s(self.binddn, self.bindpw)
            self.__ldap_conn = newconn

        return self.__ldap_conn

    @property
    def naming_context(self) -> str:
        """
        Default naming context.

        :raises ValueError: If default naming context can not be obtained.
        :rtype: str
        """
        if not self.__naming_context:
            attr = "defaultNamingContext"
            result = self.ldap_conn.search_s("", ldap.SCOPE_BASE, attrlist=[attr])
            if len(result) != 1:
                raise ValueError(f"Unexpected number of results for rootDSE query: {len(result)}")

            (_, values) = result[0]
            if attr not in values:
                raise ValueError(f"Unable to find {attr}")

            self.__naming_context = str(values[attr][0].decode("utf-8"))

        return self.__naming_context

    def disconnect(self) -> None:
        """
        Disconnect LDAP connection.
        """
        if self.__ldap_conn is not None:
            self.__ldap_conn.unbind()
            self.__ldap_conn = None

    def ldap_result_to_dict(
        self, result: list[tuple[str, dict[str, list[bytes]]]]
    ) -> dict[str, dict[str, list[bytes]]]:
        """
        Convert result from python-ldap library from tuple into a dictionary
        to simplify lookup by distinguished name.

        :param result: Search result from python-ldap.
        :type result: tuple[str, dict[str, list[bytes]]]
        :return: Dictionary with distinguished name as key and attributes as value.
        :rtype: dict[str, dict[str, list[bytes]]]
        """
        return dict((dn, attrs) for dn, attrs in result if dn is not None)

    def start(self) -> None:
        self.svc.start(self.svc_name)

    def stop(self) -> None:
        self.svc.stop(self.svc_name)

    def backup(self) -> Any:
        """
        Backup all directory server data.

        Full backup of ``cn=config`` and default naming context is performed.
        This is done by simple LDAP search on given base dn and remembering the
        contents. The operation is usually very fast.

        :return: Backup data.
        :rtype: Any
        """
        self.logger.info("Creating backup of LDAP server")

        data = self.ldap_conn.search_s(self.naming_context, ldap.SCOPE_SUBTREE)
        config = self.ldap_conn.search_s("cn=config", ldap.SCOPE_BASE)
        nc = self.ldap_conn.search_s(self.naming_context, ldap.SCOPE_BASE, attrlist=["aci"])

        dct = self.ldap_result_to_dict(data)
        dct.update(self.ldap_result_to_dict(config))
        dct.update(self.ldap_result_to_dict(nc))

        return dct

    def restore(self, backup_data: Any | None) -> None:
        """
        Restore directory server data.

        Current directory server content in ``cn=config`` and default naming
        context is modified to its original data. This is done by computing a
        difference between original data obtained by :func:`backup` and then
        calling add, delete and modify operations to convert current state to
        the original state. This operation is usually very fast.

        :param backup_data: Backup data.
        :type backup_data: PurePath | Sequence[PurePath] | Any | None
        """
        if backup_data is None:
            return

        self.logger.info("Restoring LDAP server from memory")

        if not isinstance(backup_data, dict):
            raise TypeError(f"Expected dict, got {type(backup_data)}")

        data = self.ldap_conn.search_s(self.naming_context, ldap.SCOPE_SUBTREE)
        config = self.ldap_conn.search_s("cn=config", ldap.SCOPE_BASE)
        nc = self.ldap_conn.search_s(self.naming_context, ldap.SCOPE_BASE, attrlist=["aci"])

        # Convert list of tuples to dictionary for better lookup
        data = self.ldap_result_to_dict(data)
        data.update(self.ldap_result_to_dict(config))
        data.update(self.ldap_result_to_dict(nc))

        for dn, attrs in reversed(data.items()):
            # Restore records that were modified
            if dn in backup_data:
                original_attrs = backup_data[dn]
                modlist = ldap.modlist.modifyModlist(attrs, original_attrs)
                modlist = self.__filter_modlist(dn, modlist)
                if modlist:
                    self.ldap_conn.modify_s(dn, modlist)

        for dn, attrs in reversed(data.items()):
            # Delete records that were added
            if dn not in backup_data:
                self.ldap_conn.delete_s(dn)
                continue

        for dn, attrs in backup_data.items():
            # Add back records that were deleted
            if dn not in data:
                self.ldap_conn.add_s(dn, list(attrs.items()))

    def __filter_modlist(self, dn: str, modlist: list) -> list:
        """
        Remove special items that can not be modified from ``modlist``.

        :param dn: Object's DN.
        :type dn: str
        :param modlist: LDAP modlist.
        :type modlist: list
        :return: Filtered modlist.
        :rtype: list
        """
        if dn != "cn=config":
            return modlist

        result = []
        for op, attr, value in modlist:
            # We are not allowed to touch these
            if attr.startswith("nsslapd"):
                continue

            result.append((op, attr, value))

        return result
