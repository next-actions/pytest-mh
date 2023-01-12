from __future__ import annotations

from enum import unique
from typing import final

from pytest_mh import KnownTopologyBase, Topology, TopologyDomain, TopologyMark


@final
@unique
class KnownTopology(KnownTopologyBase):
    """
    Well-known topologies that can be given to ``pytest.mark.topology``
    directly. It is expected to use these values in favor of providing
    custom marker values.

    .. code-block:: python
        :caption: Example usage

        @pytest.mark.topology(KnownTopology.KDC)
        def test_kdc(client: Client, kdc: KDC):
            assert True
    """

    KDC = TopologyMark(
        name="kdc",
        topology=Topology(TopologyDomain("test", client=1, kdc=1)),
        fixtures=dict(client="test.client[0]", kdc="test.kdc[0]"),
    )
