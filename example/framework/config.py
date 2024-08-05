from __future__ import annotations

from typing import Type

from pytest_mh import MultihostConfig, MultihostDomain, MultihostHost, MultihostRole

__all__ = [
    "SUDOMultihostConfig",
    "SUDOMultihostDomain",
]


class SUDOMultihostConfig(MultihostConfig):
    @property
    def id_to_domain_class(self) -> dict[str, Type[MultihostDomain]]:
        """
        All domains are mapped to :class:`SUDOMultihostDomain`.

        :rtype: Class name.
        """
        return {"*": SUDOMultihostDomain}


class SUDOMultihostDomain(MultihostDomain[SUDOMultihostConfig]):
    @property
    def role_to_host_class(self) -> dict[str, Type[MultihostHost]]:
        """
        Map roles to classes:

        * client to ClientHost
        * ldap to LDAPHost

        :rtype: Class name.
        """
        from .hosts.client import ClientHost
        from .hosts.ldap import LDAPHost

        return {
            "client": ClientHost,
            "ldap": LDAPHost,
        }

    @property
    def role_to_role_class(self) -> dict[str, Type[MultihostRole]]:
        """
        Map roles to classes:

        * client to Client
        * ldap to LDAP

        :rtype: Class name.
        """
        from .roles.client import Client
        from .roles.ldap import LDAP

        return {
            "client": Client,
            "ldap": LDAP,
        }
