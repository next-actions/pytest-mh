from __future__ import annotations

import re
from typing import Literal

import pytest

from .. import MultihostArtifactsType, MultihostHost, MultihostUtility
from ..conn import ProcessLogLevel
from .fs import LinuxFileSystem

__all__ = ["Coredumpd"]


class Coredumpd(MultihostUtility[MultihostHost]):
    """
    Coredumpd utilities.

    Collects generated core files from /var/lib/systemd/coredump and if there
    are any, optionally fail the test.

    .. note::

        In order for this functionality to work correctly, systemd-coredumpd
        must be configured to store the core files in a directory (default), not
        in a journal.

        See ``man coredump.conf`` and its ``Storage`` option for more
        information.
    """

    def __init__(
        self,
        host: MultihostHost,
        fs: LinuxFileSystem,
        *,
        mode: Literal["fail", "warn", "ignore"] = "ignore",
        filter: str | None = None,
        path: str = "/var/lib/systemd/coredump",
    ) -> None:
        """
        ``mode`` values:

        * ``ignore``: all failures are ignored
        * ``warn``: test result category is set to "COREDUMPS" and the test is
          marked as such in a test summary, however test outcome and pytest exit
          code is kept intact
        * ``fail``: test result category is set to "COREDUMPS" and the test is
          marked as such in a test summary, if a test outcome is ``passed`` it
          is set to ``failed`` and pytest will return non-zero exit code

        :param host: Multihost host.
        :type host: MultihostHost
        :param mode: Action taken when a core file is found.
        :type mode: Literal["fail", "warn", "ignore"]
        :param filter: Regular expression used to filter the core file names,
            defaults to None
        :type filter: str | None, optional
        :param path: Path to the directory where core files are stored, defaults
            to ``/var/lib/systemd/coredump``
        :type path: str
        """
        super().__init__(host)

        self.fs: LinuxFileSystem = fs

        self.mode: Literal["fail", "warn", "ignore"] = mode
        """Action taken when a core file is found."""

        self.filter: str | None = None
        """Regular expression to filter core file names."""

        self.path: str = path
        """Path to the directory where core files are stored."""

        self._corefiles: list[str] | None = None

    def setup(self) -> None:
        """
        Backup and remove /var/lib/systemd/coredump.

        This directory will be automatically re-created by systemd-coredumpd if
        needed.
        """
        super().setup()

        self.fs.rm("/var/lib/systemd/coredump")

    def list_core_files(self) -> list[str]:
        """
        List available core files.

        :return: List of core file names.
        :rtype: list[str]
        """
        # List the folder, exit with 0 if it does not exist (no core files were produced)
        result = self.host.conn.run(
            f"[ -d '{self.path}' ] && ls -N -1 '{self.path}' || :", log_level=ProcessLogLevel.Error
        )

        return result.stdout_lines

    def parse_core_file_name(self, name: str) -> tuple[str, str]:
        """
        Parse core file name and get the PID and timestamp information.

        Expected format is core.{binary}.{bootid}.{pid}.{timestamp}[.zst]

        :param name: Core file name.
        :type name: str
        :raises ValueError: If the core file name has unexpected format.
        :return: Tuple of ``(PID, timestamp)``.
        :rtype: tuple[str, str] | None
        """
        parts = name.split(".")
        if not parts or len(parts) < 3:
            raise ValueError(f"Invalid coredump name: {name}")

        # If the file is compressed, remove the extension
        if not parts[-1].isnumeric():
            parts.pop()

        pid = parts[-2]
        timestamp = parts[-1]

        return (pid, timestamp)

    def get_artifacts_list(self, host: MultihostHost, artifacts_type: MultihostArtifactsType) -> set[str]:
        """
        Dump backtrace and other information from generated core files for easy access.

        :param host: Host where the artifacts are being collected.
        :type host: MultihostHost
        :param artifacts_type: Type of artifacts that are being collected.
        :type artifacts_type: MultihostArtifactsType
        :return: List of artifacts to collect.
        :rtype: set[str]
        """
        if self._corefiles is None:
            self._corefiles = self.list_core_files()

        if not self._corefiles:
            return set()

        # Parse PID and timestamp that we can use to get information for journal
        for name in self._corefiles:
            try:
                pid, timestamp = self.parse_core_file_name(name)
            except ValueError:
                self.logger.warn(f"Invalid core file name: {name}")
                continue

            # Dump the information
            self.host.conn.run(
                rf"""
                journalctl --output=verbose          \
                    'COREDUMP_PID={pid}'             \
                    'COREDUMP_TIMESTAMP={timestamp}' \
                    > '{self.path}/{name}.backtrace'
                """,
                log_level=ProcessLogLevel.Error,
            )

        return {self.path}

    def pytest_report_teststatus(
        self, report: pytest.CollectReport | pytest.TestReport, config: pytest.Config
    ) -> tuple[str, str, str | tuple[str, dict[str, bool]]] | None:
        """
        Report core file found error if found and matches requested filter.

        :param report: Pytest report
        :type report: pytest.CollectReport | pytest.TestReport
        :param config: Pytest config
        :type config: pytest.Config
        :return: Pytest test status
        :rtype: tuple[str, str, str | tuple[str, dict[str, bool]]] | None
        """
        if report.when != "call":
            return None

        if self.mode == "ignore" or report.outcome == "skipped":
            return None

        self.logger.info("Checking for core files")

        if self._corefiles is None:
            self._corefiles = self.list_core_files()

        if not self._corefiles:
            return None

        # Ignore if no core files matches the filter
        if self.filter:
            match = re.search(self.filter, "\n".join(self._corefiles))
            if match is None:
                return None

        original_outcome = report.outcome

        # Fail the test if fail mode is selected
        if report.outcome == "passed" and self.mode == "fail":
            report.outcome = "failed"

        # Count this test into "COREDUMPS" category in the final summary,
        # mark it with "C"/"COREDUMP" in short/verbose listing.
        return ("COREDUMPS", "C", f"{original_outcome.upper()}/COREDUMP")
