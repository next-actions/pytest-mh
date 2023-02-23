"""
.. avoid already-imported warning: PYTEST_DONT_REWRITE (hidden from sphinx)
"""
from __future__ import annotations

from ._private.fixtures import MultihostFixture, mh
from ._private.marks import KnownTopologyBase, KnownTopologyGroupBase, TopologyMark
from ._private.multihost import (
    MultihostConfig,
    MultihostDomain,
    MultihostHost,
    MultihostHostOSFamily,
    MultihostRole,
    MultihostUtility,
)
from ._private.plugin import MultihostPlugin, pytest_addoption, pytest_configure
from ._private.topology import Topology, TopologyDomain

__all__ = [
    "mh",
    "MultihostConfig",
    "MultihostDomain",
    "MultihostFixture",
    "MultihostHost",
    "MultihostHostOSFamily",
    "MultihostPlugin",
    "MultihostRole",
    "MultihostUtility",
    "pytest_addoption",
    "pytest_configure",
    "Topology",
    "TopologyDomain",
    "TopologyMark",
    "KnownTopologyBase",
    "KnownTopologyGroupBase",
]
