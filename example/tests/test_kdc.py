from __future__ import annotations

import pytest
from lib.roles.client import Client
from lib.roles.kdc import KDC
from lib.topology import KnownTopology


@pytest.mark.topology(KnownTopology.KDC)
def test_kinit(client: Client, kdc: KDC):
    kdc.principal("user-1").add(password="Secret123")

    client.kinit("user-1", realm=client.realm, password="Secret123")
    assert client.has_tgt(client.realm)

    client.kdestroy()
    assert not client.has_tgt(client.realm)


@pytest.mark.topology(KnownTopology.KDC)
def test_kvno(client: Client, kdc: KDC):
    kdc.principal("user-1").add(password="Secret123")
    kdc.principal("host/myhost").add()

    client.kinit("user-1", realm=client.realm, password="Secret123")
    assert client.has_tgt(client.realm)

    client.kvno("host/myhost", realm=client.realm)
    assert "host/myhost" in client.klist().stdout
