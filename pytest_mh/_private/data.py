from __future__ import annotations

import pytest

from .marks import TopologyMark
from .multihost import MultihostConfig


class MultihostItemData(object):
    """
    Multihost internal pytest data, stored in :attr:`pytest.Item.multihost`
    """

    def __init__(self, multihost: MultihostConfig | None, topology_mark: TopologyMark | None) -> None:
        self.multihost: MultihostConfig | None = multihost
        """
        Multihost object.
        """

        self.topology_mark: TopologyMark | None = topology_mark
        """
        Topology mark for the test run.
        """

        self.outcome: str | None = None
        """
        Test run outcome, available in fixture finalizers.
        """

    def _init(self) -> None:
        """
        Postponed initialization. This is called once we know that current
        mh configuration supports desired topology.
        """
        # Initialize topology controller
        if self.multihost is not None and self.topology_mark is not None:
            self.topology_mark.controller._init(
                self.topology_mark.name,
                self.multihost,
                self.multihost.logger,
                self.topology_mark.topology,
                self.topology_mark.fixtures,
            )

    @staticmethod
    def SetData(item: pytest.Item, data: MultihostItemData | None) -> None:
        item.stash[DataStashKey] = data

    @staticmethod
    def GetData(item: pytest.Item) -> MultihostItemData | None:
        return item.stash[DataStashKey]


DataStashKey = pytest.StashKey[MultihostItemData | None]()
