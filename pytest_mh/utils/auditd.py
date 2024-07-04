from __future__ import annotations

import re
from typing import Literal

import pytest

from .. import MultihostHost, MultihostUtility
from ..conn import ProcessLogLevel

__all__ = ["Auditd"]


class Auditd(MultihostUtility[MultihostHost]):
    """
    Auditd utilities.

    Collects audit logs and detects AVC denials.
    """

    def __init__(
        self,
        host: MultihostHost,
        *,
        avc_mode: Literal["fail", "warn", "ignore"],
        avc_filter: str | None = None,
    ) -> None:
        """
        ``avc_mode`` values:

        * ``ignore``: all failures are ignored
        * ``warn``: test result category is set to "AVC DENIALS" and the test is
          marked as such in a test summary, however test outcome and pytest exit
          code is kept intact
        * ``fail``: test result category is set to "AVC DENIALS" and the test is
          marked as such in a test summary, if a test outcome is ``passed`` it
          is set to ``failed`` and pytest will return non-zero exit code

        :param host: Multihost host.
        :type host: MultihostHost
        :param avc_mode: Action taken when AVC denial is found in audit logs.
        :type avc_mode: Literal["fail", "warn", "ignore"]
        :param avc_filter: Regular expression used to filter the AVC denials,
            defaults to None
        :type avc_filter: str | None, optional
        """
        super().__init__(host)

        self.avc_mode: Literal["fail", "warn", "ignore"] = avc_mode
        self.avc_filter: str | None = avc_filter

        self.artifacts: set[str] = {"/var/log/audit/audit.log"}
        self._backup: str | None = None
        self._auditd_running: bool = False

    def setup(self) -> None:
        """
        Create backup of audit logs and clear them for current test run.
        """
        super().setup()

        result = self.host.conn.run(
            """
            set -e

            if [ ! -d /var/log/audit ]; then
                exit 0
            fi

            tmp=`mktemp -d`
            cp -r --archive /var/log/audit "$tmp"
            truncate --size 0 /var/log/audit/audit.log*
            echo $tmp
            """,
            log_level=ProcessLogLevel.Error,
        )

        tmp_path = result.stdout.strip()
        if tmp_path:
            self._auditd_running = True
            self._backup = tmp_path

    def teardown(self) -> None:
        """
        Restore previous audit logs from backup and remove the backup.
        """
        if self._backup is not None:
            self.host.conn.run(
                f"""
                set -e

                for f in "{self._backup}"/audit/audit.log*; do
                    name=`basename "$f"`
                    cat "$f" > "/var/log/audit/$name"
                done

                rm -fr "{self._backup}"
                """,
                log_level=ProcessLogLevel.Error,
            )

        return super().teardown()

    def pytest_report_teststatus(
        self, report: pytest.CollectReport | pytest.TestReport, config: pytest.Config
    ) -> tuple[str, str, str | tuple[str, dict[str, bool]]] | None:
        """
        Report AVC denial error if found and matches requested filter.

        :param report: Pytest report
        :type report: pytest.CollectReport | pytest.TestReport
        :param config: Pytest config
        :type config: pytest.Config
        :return: Pytest test status
        :rtype: tuple[str, str, str | tuple[str, dict[str, bool]]] | None
        """
        if report.when != "call":
            return None

        if not self._auditd_running or self.avc_mode == "ignore" or report.outcome == "skipped":
            return None

        self.logger.info("Checking for AVC denials")

        result = self.host.conn.run(
            "ausearch --input-logs -m AVC,USER_AVC", raise_on_error=False, log_level=ProcessLogLevel.Silent
        )
        if result.rc:
            return None

        records = result.stdout
        if not records:
            return None

        # Ignore if no message matches the filter
        if self.avc_filter:
            match = re.search(self.avc_filter, records)
            if match is None:
                return None

        original_outcome = report.outcome

        # Fail the test if fail mode is selected
        if report.outcome == "passed" and self.avc_mode == "fail":
            report.outcome = "failed"

        # Count this test into "AVC DENIALS" category in the final summary,
        # mark it with "A"/"AVC DENIAL" in short/verbose listing.
        return ("AVC DENIALS", "A", f"{original_outcome.upper()}/AVC DENIAL")
