from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

import pytest

from .. import MultihostArtifactsType, MultihostHost, MultihostUtility
from ..conn import ProcessLogLevel
from .fs import LinuxFileSystem

__all__ = ["Coredumpd"]


class Coredumpd(MultihostUtility[MultihostHost]):
    """
    Coredumpd utilities.

    Detects core dumps generated during the current test using ``coredumpctl``
    and, if there are any, optionally fails the test. For each core dump a human
    readable backtrace and a compressed core file are collected as artifacts.

    Core dumps are matched by their timestamp against
    :attr:`MultihostHost.test_start_timestamp`, so only core dumps produced
    during the current test are considered.
    """

    def __init__(
        self,
        host: MultihostHost,
        fs: LinuxFileSystem,
        *,
        mode: Literal["fail", "warn", "ignore"] = "ignore",
        filter: str | None = None,
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
        :param fs: Linux file system utility, used to create a temporary
            directory for the collected artifacts.
        :type fs: LinuxFileSystem
        :param mode: Action taken when a core file is found.
        :type mode: Literal["fail", "warn", "ignore"]
        :param filter: Regular expression used to filter the core dumps by the
            executable path, defaults to None
        :type filter: str | None, optional
        """
        super().__init__(host)

        self.fs: LinuxFileSystem = fs

        self.mode: Literal["fail", "warn", "ignore"] = mode
        """Action taken when a core file is found."""

        self.filter: str | None = filter
        """Regular expression to filter core dumps by the executable path."""

        self._coredumps: list[dict[str, Any]] | None = None

    def list_coredumps(self) -> list[dict[str, Any]]:
        """
        List core dumps produced during the current test.

        Only core dumps created at or after
        :attr:`MultihostHost.test_start_timestamp` are returned, so core dumps
        left over from previous tests are ignored.

        :return: List of ``coredumpctl`` entries (parsed JSON objects).
        :rtype: list[dict[str, Any]]
        """
        since = self.host.test_start_timestamp

        # coredumpctl exits with non-zero code and prints "No coredumps found."
        # when there are no matching core dumps.
        result = self.host.conn.run(
            f"coredumpctl list --since @{since} --no-legend --json=short",
            log_level=ProcessLogLevel.Error,
            raise_on_error=False,
        )

        if result.rc != 0 or not result.stdout.strip():
            return []

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.logger.warning("Unable to parse coredumpctl output")
            return []

    def get_artifacts_list(self, host: MultihostHost, artifacts_type: MultihostArtifactsType) -> set[str]:
        """
        Collect a backtrace and a compressed core file for each core dump.

        :param host: Host where the artifacts are being collected.
        :type host: MultihostHost
        :param artifacts_type: Type of artifacts that are being collected.
        :type artifacts_type: MultihostArtifactsType
        :return: List of artifacts to collect.
        :rtype: set[str]
        """
        if self._coredumps is None:
            self._coredumps = self.list_coredumps()

        if not self._coredumps:
            return set()

        # Core dumps are collected into /var/coredumps so they are clearly
        # visible in the artifacts list, falling back to a random temporary
        # directory if that location is not writable. The directory is
        # automatically removed when the file system utility is torn down,
        # which happens after the artifacts are collected.
        outdir = self.fs.mkdtemp(path="/var/coredumps")
        artifacts: set[str] = set()

        for dump in self._coredumps:
            pid = dump.get("pid")
            if pid is None:
                continue

            exe = dump.get("exe") or "unknown"
            timestamp = dump.get("time")
            name = f"core.{os.path.basename(exe)}.{pid}.{timestamp}"

            info_path = f"{outdir}/{name}.info"
            core_path = f"{outdir}/{name}.core.zst"

            # Dump a human readable backtrace.
            self.host.conn.run(
                f"coredumpctl info {pid} > '{info_path}'",
                log_level=ProcessLogLevel.Error,
                raise_on_error=False,
            )
            artifacts.add(info_path)

            # Dump and compress the core file. The core data may not be available
            # anymore (e.g. the core file was already removed), in which case
            # coredumpctl returns non-zero and we only keep the backtrace.
            result = self.host.conn.run(
                f"set -o pipefail; coredumpctl dump {pid} 2>/dev/null | zstd -q -o '{core_path}'",
                log_level=ProcessLogLevel.Error,
                raise_on_error=False,
            )

            if result.rc == 0:
                artifacts.add(core_path)
            else:
                self.logger.warning(f"Unable to dump core file for PID {pid} ({exe})")
                self.host.conn.run(f"rm --force '{core_path}'", log_level=ProcessLogLevel.Error, raise_on_error=False)

        return artifacts

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

        if self._coredumps is None:
            self._coredumps = self.list_coredumps()

        if not self._coredumps:
            return None

        # Ignore if no core dump's executable matches the filter
        if self.filter:
            executables = "\n".join(str(dump.get("exe", "")) for dump in self._coredumps)
            if re.search(self.filter, executables) is None:
                return None

        original_outcome = report.outcome

        # Fail the test if fail mode is selected
        if report.outcome == "passed" and self.mode == "fail":
            report.outcome = "failed"

        # Count this test into "COREDUMPS" category in the final summary,
        # mark it with "C"/"COREDUMP" in short/verbose listing.
        return ("COREDUMPS", "C", f"{original_outcome.upper()}/COREDUMP")
