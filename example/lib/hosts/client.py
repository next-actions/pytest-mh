from __future__ import annotations

from pytest_mh import MultihostHost

from ..config import ExampleMultihostDomain


class ClientHost(MultihostHost[ExampleMultihostDomain]):
    """
    Kerberos client host object.

    Provides features specific to Kerberos client.

    This class adds ``config.realm``, ``config.krbdomain`` and ``config.kdc``
    multihost configuration options to set the default kerberos realm,
    domain and the kdc hostname.

    .. code-block:: yaml
        :caption: Example multihost configuration
        :emphasize-lines: 6-8

        - hostname: client.test
          role: client
          username: root
          password: Secret123
          config:
            realm: TEST
            krbdomain: test
            kdc: kdc.test

    .. note::

        Full backup and restore is supported.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.realm: str = self.config.get("realm", "TEST")
        self.krbdomain: str = self.config.get("krbdomain", "test")
        self.kdc: str = self.config.get("kdc", "kdc.test")
