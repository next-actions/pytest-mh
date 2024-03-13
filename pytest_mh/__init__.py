"""
.. avoid already-imported warning: PYTEST_DONT_REWRITE (hidden from sphinx)
"""

from __future__ import annotations

from ._private.artifacts import MultihostHostArtifacts, MultihostTopologyControllerArtifacts
from ._private.data import MultihostItemData
from ._private.fixtures import MultihostFixture, mh
from ._private.marks import KnownTopologyBase, KnownTopologyGroupBase, TopologyMark
from ._private.multihost import (
    MultihostConfig,
    MultihostDomain,
    MultihostHost,
    MultihostOSFamily,
    MultihostRole,
    MultihostUtility,
)
from ._private.plugin import MultihostPlugin, pytest_addoption, pytest_configure
from ._private.topology import Topology, TopologyDomain
from ._private.topology_controller import TopologyController

__all__ = [
    "mh",
    "KnownTopologyBase",
    "KnownTopologyGroupBase",
    "MultihostConfig",
    "MultihostDomain",
    "MultihostFixture",
    "MultihostHost",
    "MultihostHostArtifacts",
    "MultihostItemData",
    "MultihostOSFamily",
    "MultihostPlugin",
    "MultihostRole",
    "MultihostTopologyControllerArtifacts",
    "MultihostUtility",
    "pytest_addoption",
    "pytest_configure",
    "Topology",
    "TopologyController",
    "TopologyDomain",
    "TopologyMark",
]
