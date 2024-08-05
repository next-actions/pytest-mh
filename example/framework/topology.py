"""Predefined well-known topologies."""

from __future__ import annotations

from enum import unique
from typing import final

from pytest_mh import KnownTopologyBase, KnownTopologyGroupBase, Topology, TopologyDomain, TopologyMark

from .topology_controllers import LDAPTopologyController, SSSDTopologyController, SudoersTopologyController

__all__ = [
    "KnownTopology",
    "KnownTopologyGroup",
]


@final
@unique
class KnownTopology(KnownTopologyBase):
    """
    Well-known topologies that can be given to ``pytest.mark.topology``
    directly. It is expected to use these values in favor of providing
    custom marker values.

    .. code-block:: python
        :caption: Example usage

        @pytest.mark.topology(KnownTopology.LDAP)
        def test_ldap(client: Client, ldap: LDAP):
            assert True
    """

    Sudoers = TopologyMark(
        name="sudoers",
        topology=Topology(TopologyDomain("sudo", client=1)),
        controller=SudoersTopologyController(),
        fixtures=dict(client="sudo.client[0]", provider="sudo.client[0]"),
    )

    LDAP = TopologyMark(
        name="ldap",
        topology=Topology(TopologyDomain("sudo", client=1, ldap=1)),
        controller=LDAPTopologyController(),
        fixtures=dict(client="sudo.client[0]", ldap="sudo.ldap[0]", provider="sudo.ldap[0]"),
    )

    SSSD = TopologyMark(
        name="sssd",
        topology=Topology(TopologyDomain("sudo", client=1, ldap=1)),
        controller=SSSDTopologyController(),
        fixtures=dict(client="sudo.client[0]", ldap="sudo.ldap[0]", provider="sudo.ldap[0]"),
    )


class KnownTopologyGroup(KnownTopologyGroupBase):
    """
    Groups of well-known topologies that can be given to ``pytest.mark.topology``
    directly. It is expected to use these values in favor of providing
    custom marker values.

    The test is parametrized and runs multiple times, once per each topology.

    .. code-block:: python
        :caption: Example usage (runs on AD, IPA, LDAP and Samba topology)

        @pytest.mark.topology(KnownTopologyGroup.AnyProvider)
        def test_ldap(client: Client, provider: GenericProvider):
            assert True
    """

    AnyProvider = [KnownTopology.Sudoers, KnownTopology.LDAP, KnownTopology.SSSD]
