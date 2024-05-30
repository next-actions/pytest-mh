"""
.. avoid already-imported warning: PYTEST_DONT_REWRITE (hidden from sphinx)
"""

from __future__ import annotations

from ._private.artifacts import MultihostArtifactsType, MultihostHostArtifacts, MultihostTopologyControllerArtifacts
from ._private.data import MultihostItemData
from ._private.fixtures import MultihostFixture, mh
from ._private.marks import KnownTopologyBase, KnownTopologyGroupBase, TopologyMark
from ._private.multihost import (
    MultihostConfig,
    MultihostDomain,
    MultihostHost,
    MultihostOSFamily,
    MultihostReentrantUtility,
    MultihostRole,
    MultihostUtility,
    mh_utility,
    mh_utility_ignore_use,
    mh_utility_postpone_setup,
    mh_utility_used,
)
from ._private.plugin import MultihostPlugin, mh_fixture, pytest_addoption, pytest_configure
from ._private.topology import Topology, TopologyDomain
from ._private.topology_controller import TopologyController

__all__ = [
    "mh",
    "KnownTopologyBase",
    "KnownTopologyGroupBase",
    "MultihostArtifactsType",
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
    "MultihostReentrantUtility",
    "mh_utility",
    "mh_utility_postpone_setup",
    "mh_utility_ignore_use",
    "mh_utility_used",
    "mh_fixture",
    "pytest_addoption",
    "pytest_configure",
    "Topology",
    "TopologyController",
    "TopologyDomain",
    "TopologyMark",
]
