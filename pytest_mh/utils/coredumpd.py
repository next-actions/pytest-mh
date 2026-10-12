from __future__ import annotations

import fnmatch
import json
import os
import re
from typing import Any, Literal, TypedDict

import pytest

from .. import MHReportTestStatus, MultihostArtifactsType, MultihostHost, MultihostUtility
from ..conn import ProcessLogLevel
from .fs import LinuxFileSystem

__all__ = ["Coredumpd", "CoredumpFilter"]

# Severity ordering used to combine the per-core-dump filter result with the mode.
_SEVERITY_RANK: dict[str, int] = {"ignore": 0, "warn": 1, "fail": 2}


class CoredumpFilter(TypedDict, total=False):
    """
    Patterns used to classify core dumps by their executable path.

    Each action takes a list of patterns matched against the executable path of a
    core dump. A pattern can be:

    * ``re:<regex>``: a regular expression (:func:`re.search`) matched against the
      full executable path, e.g. ``re:/usr/libexec/sssd/.*``
    * a full path (contains a ``/``): a shell-style glob (:func:`fnmatch.fnmatchcase`)
      matched against the executable path, e.g. ``/usr/libexec/sssd/sssd_be`` or
      ``/usr/libexec/sssd/*``
    * a bare binary name (no ``/``): a shell-style glob matched against the base
      name of the executable path, e.g. ``sssd_be`` or ``sssd*``

    A plain string without wildcards matches exactly.

    A core dump matches an action if any of its patterns match. A core dump that
    matches ``fail`` always fails the test and a core dump that matches ``ignore``
    is always ignored, regardless of the configured mode. A core dump that matches
    neither is handled according to the mode.
    """

    fail: list[str]
    """Core dumps whose executable matches any of these patterns always fail the test."""

    ignore: list[str]
    """Core dumps whose executable matches any of these patterns are always ignored."""


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
        filter: CoredumpFilter | None = None,
    ) -> None:
        """
        Each core dump results in one of the following actions based on its
        executable path (see :class:`CoredumpFilter`):

        * ``ignore``: the core dump is collected as an artifact but it does not
          affect the test outcome or category
        * ``warn``: test result category is set to "COREDUMPS" and the test is
          marked as such in a test summary, however test outcome and pytest exit
          code is kept intact
        * ``fail``: test result category is set to "COREDUMPS" and the test is
          marked as such in a test summary, if a test outcome is ``passed`` it
          is set to ``failed`` and pytest will return non-zero exit code

        A core dump that matches the ``fail`` filter always fails the test and a
        core dump that matches the ``ignore`` filter is always ignored. A core
        dump that matches neither (an unexpected core dump in a random binary) is
        handled according to ``mode``: it fails the test if ``mode="fail"``, only
        warns if ``mode="warn"`` or is ignored if ``mode="ignore"``.

        :param host: Multihost host.
        :type host: MultihostHost
        :param fs: Linux file system utility, used to create a temporary
            directory for the collected artifacts.
        :type fs: LinuxFileSystem
        :param mode: Action taken for a core dump that does not match any filter,
            defaults to ``ignore``.
        :type mode: Literal["fail", "warn", "ignore"]
        :param filter: Patterns used to classify core dumps by the executable
            path (see :class:`CoredumpFilter`), defaults to None
        :type filter: CoredumpFilter | None, optional
        """
        super().__init__(host)

        self.fs: LinuxFileSystem = fs

        self.mode: Literal["fail", "warn", "ignore"] = mode
        """Action taken for a core dump that does not match any filter."""

        self.filter: CoredumpFilter = filter if filter is not None else {}
        """Patterns to classify core dumps by the executable path."""

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

    @staticmethod
    def _match(pattern: str, exe: str) -> bool:
        """
        Match a single filter pattern against an executable path.

        :param pattern: Filter pattern (see :class:`CoredumpFilter`).
        :type pattern: str
        :param exe: Executable path of the core dump.
        :type exe: str
        :return: True if the pattern matches the executable path.
        :rtype: bool
        """
        if pattern.startswith("re:"):
            return re.search(pattern[len("re:") :], exe) is not None

        if "/" in pattern:
            return fnmatch.fnmatchcase(exe, pattern)

        return fnmatch.fnmatchcase(os.path.basename(exe), pattern)

    def classify(self, exe: str) -> Literal["fail", "warn", "ignore"]:
        """
        Classify a core dump into an action based on its executable path.

        A core dump matching the ``fail`` filter always fails and one matching the
        ``ignore`` filter is always ignored. A core dump that matches neither is
        handled according to :attr:`mode`.

        :param exe: Executable path of the core dump.
        :type exe: str
        :return: Action to take for the core dump.
        :rtype: Literal["fail", "warn", "ignore"]
        """
        if any(self._match(pattern, exe) for pattern in self.filter.get("fail", [])):
            return "fail"
        if any(self._match(pattern, exe) for pattern in self.filter.get("ignore", [])):
            return "ignore"

        return self.mode

    def pytest_report_teststatus(
        self, report: pytest.CollectReport | pytest.TestReport, config: pytest.Config
    ) -> MHReportTestStatus | None:
        """
        Report core file found error if found and matches requested filter.

        :param report: Pytest report
        :type report: pytest.CollectReport | pytest.TestReport
        :param config: Pytest config
        :type config: pytest.Config
        :return: Pytest test status
        :rtype: MHReportTestStatus | None
        """
        if report.when != "call":
            return None

        if report.outcome == "skipped":
            return None

        self.logger.info("Checking for core files")

        if self._coredumps is None:
            self._coredumps = self.list_coredumps()

        if not self._coredumps:
            return None

        # Take the most severe action across all collected core dumps.
        action = "ignore"
        for dump in self._coredumps:
            severity = self.classify(str(dump.get("exe", "")))
            if _SEVERITY_RANK[severity] > _SEVERITY_RANK[action]:
                action = severity

        if action == "ignore":
            return None

        original_outcome = report.outcome

        # Fail the test if the effective action is "fail"
        if report.outcome == "passed" and action == "fail":
            report.outcome = "failed"

        # Count this test into "COREDUMPS" category in the final summary,
        # mark it with "C"/"COREDUMP" in short/verbose listing.
        return MHReportTestStatus(
            status=("COREDUMPS", "C", f"{original_outcome.upper()}/COREDUMP"),
            force_artifacts_collection=True,
        )
