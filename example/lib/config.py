from __future__ import annotations

from typing import Type

from pytest_mh import MultihostConfig, MultihostDomain, MultihostHost, MultihostRole


class ExampleMultihostConfig(MultihostConfig):
    @property
    def id_to_domain_class(self) -> dict[str, Type[MultihostDomain]]:
        """
        Map domain id to domain class. Asterisk ``*`` can be used as fallback
        value.

        :rtype: Class name.
        """
        return {"*": ExampleMultihostDomain}


class ExampleMultihostDomain(MultihostDomain[ExampleMultihostConfig]):
    @property
    def role_to_host_class(self) -> dict[str, Type[MultihostHost]]:
        """
        Map role to host class. Asterisk ``*`` can be used as fallback value.

        :rtype: Class name.
        """
        from .hosts.client import ClientHost
        from .hosts.kdc import KDCHost

        return {
            "client": ClientHost,
            "kdc": KDCHost,
        }

    @property
    def role_to_role_class(self) -> dict[str, Type[MultihostRole]]:
        """
        Map role to role class. Asterisk ``*`` can be used as fallback value.

        :rtype: Class name.
        """
        from .roles.client import Client
        from .roles.kdc import KDC

        return {
            "client": Client,
            "kdc": KDC,
        }
