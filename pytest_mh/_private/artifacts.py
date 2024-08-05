from __future__ import annotations

import tarfile
from base64 import b64decode
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias, get_args

from ..conn import ProcessLogLevel
from .errors import ArtifactsExceptionGroup
from .misc import sanitize_path, should_collect_artifacts
from .types import MultihostOSFamily, MultihostOutcome

if TYPE_CHECKING:
    from .logging import MultihostLogger
    from .multihost import MultihostHost


# +DOCS/MultihostArtifactsType
MultihostArtifactsType: TypeAlias = Literal[
    "pytest_setup", "pytest_teardown", "topology_setup", "topology_teardown", "test"
]
"""
Multihost artifacts type.

* ``pytest_setup``: collected after :meth:`MultihostHost.pytest_setup`
* ``pytest_teardown``: collected after :meth:`MultihostHost.pytest_teardown`
* ``topology_setup``: collected after :meth:`TopologyController.topology_setup`
* ``topology_teardown``: collected after :meth:`TopologyController.topology_teardown`
* ``test``: collected after each test run
"""
# -DOCS/MultihostArtifactsType


MultihostArtifactsMode: TypeAlias = Literal["never", "on-failure", "always"]
"""
Multihost artifacts mode.

Defines if artifacts should be collected or not.
"""


class MultihostHostArtifacts(object):
    """
    Manage set of artifacts that are collected at specific places.
    """

    def __init__(self, config: list[str] | dict[str, list[str]] | None = None) -> None:
        self.pytest_setup: set[str] = set()
        """
        List of artifacts collected for host after initial pytest_setup.

        See :meth:`MultihostHost.pytest_setup`.
        """

        self.pytest_teardown: set[str] = set()
        """
        List of artifacts collected for host after final pytest_teardown.

        See :meth:`MultihostHost.pytest_teardown`.
        """

        self.test: set[str] = set()
        """
        List of artifacts collected for a test when the test run is finished.
        """

        if config is not None:
            if isinstance(config, list):
                self.test = set(config)
            elif isinstance(config, dict):
                allowed = ["pytest_setup", "pytest_teardown", "test"]
                for key in config.keys():
                    if key not in allowed:
                        raise ValueError(f"Invalid key: {key}, expected {allowed}")

                self.pytest_setup = set(config.get("pytest_setup", set()))
                self.pytest_teardown = set(config.get("pytest_teardown", set()))
                self.test = set(config.get("test", set()))
            else:
                raise TypeError(f"Unsupported type: {type(config)}, expected list or dict")

    def get(self, artifacts_type: MultihostArtifactsType) -> set[str]:
        """
        Get list of artifacts by type.

        :param artifacts_type: Type to retrieve.
        :type artifacts_type: MultihostArtifactsType
        :raises ValueError: If invalid artifacts type is given.
        :return: List of artifacts.
        :rtype: set[str]
        """
        allowed = get_args(MultihostArtifactsType)
        if artifacts_type not in allowed:
            raise ValueError(f"Invalid artifacts type {artifacts_type}, expected {allowed}")

        if not hasattr(self, artifacts_type):
            return set()

        return getattr(self, artifacts_type)


class MultihostTopologyControllerArtifacts(object):
    """
    Manage set of artifacts that are collected at specific places.
    """

    def __init__(self) -> None:
        self.topology_setup: dict[MultihostHost, set[str]] = {}
        """
        List of artifacts collected for host after initial topology_setup.

        See :meth:`TopologyController.topology_setup`.
        """

        self.topology_teardown: dict[MultihostHost, set[str]] = {}
        """
        List of artifacts collected for host after final topology_teardown.

        See :meth:`TopologyController.topology_teardown`.
        """

        self.test: dict[MultihostHost, set[str]] = {}
        """
        List of artifacts collected for host when a test run is finished.
        """

    def get(self, host: MultihostHost, artifacts_type: MultihostArtifactsType) -> set[str]:
        """
        Get list of artifacts by host and type.

        :param artifacts_type: Type to retrieve.
        :type artifacts_type: MultihostArtifactsType
        :raises ValueError: If invalid artifacts type is given.
        :return: List of artifacts.
        :rtype: set[str]
        """
        allowed = get_args(MultihostArtifactsType)
        if artifacts_type not in allowed:
            raise ValueError(f"Invalid artifacts type {artifacts_type}, expected {allowed}")

        if not hasattr(self, artifacts_type):
            return set()

        artifacts: dict[MultihostHost, set[str]] = getattr(self, artifacts_type)
        return artifacts.get(host, set())


class MultihostArtifactsCollectable(Protocol):
    """
    Protocol: object supports artifacts collection.
    """

    def get_artifacts_list(self, host: MultihostHost, artifacts_type: MultihostArtifactsType) -> set[str]:
        """
        Return the list of artifacts to collect.

        This just returns :attr:`artifacts`, but it is possible to override this
        method in order to generate additional artifacts that were not created
        by the test, or detect which artifacts were created and update the
        artifacts list.

        :param host: Host where the artifacts are being collected.
        :type host: MultihostHost
        :param artifacts_type: Type of artifacts that are being collected.
        :type artifacts_type: MultihostArtifactsType
        :return: List of artifacts to collect.
        :rtype: set[str]
        """
        pass


class MultihostArtifactsCollector(object):
    """
    Multihost artifacts collector.
    """

    def __init__(
        self,
        *,
        host: MultihostHost,
        path: Path | str,
        mode: MultihostArtifactsMode,
        compress: bool,
    ) -> None:
        """
        :param host: MultihostHost object.
        :type host: MultihostHost
        :param path: Artifacts directory path.
        :type path: Path | str
        :param mode: Artifacts collection mode.
        :type mode: MultihostArtifactsMode
        :param compress: Store artifacts in compressed tarball or not?
        :type compress: bool
        """
        self.path: Path = Path(path)
        self.host: MultihostHost = host
        self.logger: MultihostLogger = host.logger
        self.mode: MultihostArtifactsMode = mode
        self.compress: bool = compress

    def should_collect(self, outcome: MultihostOutcome) -> bool:
        """
        Match mode and outcome in order to decide if artifacts should be
        collected/written or not.

        :param outcome: Test or operation outcome.
        :type outcome: MultihostOutcome
        :raises ValueError: If mode is not recognized.
        :return: True if artifacts should be collected, False otherwise.
        :rtype: bool
        """
        return should_collect_artifacts(self.mode, outcome)

    def collect(
        self,
        artifacts_type: MultihostArtifactsType,
        *,
        path: str,
        outcome: MultihostOutcome,
        collect_objects: list[MultihostArtifactsCollectable],
    ) -> None:
        """
        Collect artifacts to $artifacts_dir/$path/$collection_path.

        :param artifacts_type: Artifacts type.
        :type artifacts_type: MultihostArtifactsType
        :param path: Artifacts path relative to artifacts directory.
        :type path: str
        :param outcome: Test or operation outcome.
        :type outcome: MultihostOutcome
        :param collect_objects: Objects from which artifacts will be collected.
        :type collect_objects: list[MultihostArtifactCollectionType]
        :raises Exception: If error happens when obtaining artifacts list.
        :raises NotImplementedError: If an attempt to collect artifacts on Windows host is performed.
        :raises ValueError: If host with unknown operating system is given.
        """
        if not self.should_collect(outcome):
            self.logger.info("Artifacts are not collected")
            return

        # Substitute problematic characters and create destination path
        dest = self.path / sanitize_path(path)

        # Gather list of artifacts to collect
        errors = []
        artifacts_set: set[str] = set()
        for obj in collect_objects:
            try:
                artifacts_set.update(obj.get_artifacts_list(self.host, artifacts_type))
            except Exception as e:
                errors.append(e)

        if errors:
            raise ArtifactsExceptionGroup("Unable to collect artifacts from all hosts", errors)

        # Sort artifacts by name
        artifacts = sorted(artifacts_set)
        if not artifacts:
            self.logger.info("No artifacts to collect.")
            return

        self.logger.info(
            "Collecting artifacts",
            extra={
                "data": {
                    "Local destination": dest if not self.compress else f"{dest}.tgz",
                    "Artifacts": artifacts,
                }
            },
        )

        # Create output directory, skip the last part since it is the
        # tarball/collection name.
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Collect artifacts
        match self.host.os_family:
            case MultihostOSFamily.Linux:
                command = f"""
                    tmp=`mktemp /tmp/mh.host.artifacts.XXXXXXXXX`
                    tar -hczvf "$tmp" {' '.join([f'$(compgen -G "{x}")' for x in artifacts])} &> /dev/null
                    base64 "$tmp"
                    rm -f "$tmp" &> /dev/null
                """
            case MultihostOSFamily.Windows:
                raise NotImplementedError("Artifacts are not supported on Windows machine")
            case _:
                raise ValueError(f"Unknown operating system: {self.host.os_family}")

        result = self.host.conn.run(command, log_level=ProcessLogLevel.Error)

        # Return if no artifacts were obtained
        if not result.stdout:
            return

        with BytesIO(b64decode(result.stdout)) as buffer:
            if self.compress:
                # Store artifacts in single archive
                with open(f"{dest}.tgz", "wb") as f:
                    f.write(buffer.getbuffer())
            else:
                # Extract archive for convenience
                with tarfile.open(fileobj=buffer) as tar:
                    tar.extractall(str(dest))
