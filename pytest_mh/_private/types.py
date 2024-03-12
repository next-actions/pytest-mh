from __future__ import annotations

from typing import Literal, Protocol, TypeAlias

MultihostArtifactsType: TypeAlias = Literal[
    "test", "pytest_setup", "pytest_teardown", "topology_setup", "topology_teardown"
]
MultihostArtifactsMode: TypeAlias = Literal["never", "on-failure", "always"]
MultihostOutcome: TypeAlias = Literal["passed", "failed", "skipped", "error", "unknown"]


class MultihostArtifactCollectionType(Protocol):
    """
    Hints that given object supports artifacts collection.
    """

    def get_artifacts_list(self, type: MultihostArtifactsType) -> set[str]:
        """
        Return the list of artifacts to collect.

        This just returns :attr:`artifacts`, but it is possible to override this
        method in order to generate additional artifacts that were not created
        by the test, or detect which artifacts were created and update the
        artifacts list.

        :param type: Type of artifacts that are being collected.
        :type type: MultihostArtifactsType
        :return: List of artifacts to collect.
        :rtype: set[str]
        """
        pass
