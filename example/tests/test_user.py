from __future__ import annotations

import pytest
from framework.roles.base import GenericProvider
from framework.roles.client import Client
from framework.roles.ldap import LDAP
from framework.topology import KnownTopologyGroup


@pytest.mark.topology(KnownTopologyGroup.AnyProvider)
def test_user__passwd(client: Client, provider: GenericProvider):
    u = provider.user("tuser").add(password="Secret123")
    provider.sudorule("test-rule").add(user=u, command="ALL")

    # LDAP and SSSD topology uses SSSD for id and/or sudo rules
    # Since sudo rules are fetch in periodic task, we must start SSSD after
    # the rule is created in LDAP to avoid race conditions.
    if isinstance(provider, LDAP):
        client.svc.start("sssd.service")

    assert client.sudo.list(u.name, "Secret123", expected=["(root) ALL"])
    assert client.sudo.run(u.name, "Secret123", command="ls /root")


@pytest.mark.topology(KnownTopologyGroup.AnyProvider)
def test_user__nopasswd(client: Client, provider: GenericProvider):
    u = provider.user("tuser").add(password="Secret123")
    provider.sudorule("test-rule").add(user=u, command="ALL", nopasswd=True)

    # LDAP and SSSD topology uses SSSD for id and/or sudo rules
    # Since sudo rules are fetch in periodic task, we must start SSSD after
    # the rule is created in LDAP to avoid race conditions.
    if isinstance(provider, LDAP):
        client.svc.start("sssd.service")

    assert client.sudo.list(u.name, "Secret123", expected=["(root) NOPASSWD: ALL"])
    assert client.sudo.run(u.name, command="ls /root")
