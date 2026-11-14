from __future__ import annotations

import re
from typing import Any

from pytest_mh.cli import CLIBuilder, CLIBuilderArgs

from .. import MultihostArtifactsType, MultihostHost, MultihostUtility
from ..conn import ProcessLogLevel, ProcessResult

__all__ = ["JournaldUtils"]


class JournaldUtils(MultihostUtility[MultihostHost]):
    """
    Perform journald related tasks.
    """

    def __init__(self, host: MultihostHost) -> None:
        """
        :param host: Remote host instance.
        :type host: MultihostHost
        """
        super().__init__(host)

        self.host: MultihostHost = host

        self._cursor: int | None = None
        """Start of the current journal window; overrides the test start when set by :meth:`clear`."""

    @property
    def now(self) -> int:
        """
        :return: Current UNIX timestamp (UTC seconds) from the host clock.
        :rtype: int
        """
        return int(self.host.conn.exec(["date", "+%s"], log_level=ProcessLogLevel.Error).stdout.strip())

    def get_artifacts_list(self, host: MultihostHost, artifacts_type: MultihostArtifactsType) -> set[str]:
        """
        Dump journald into file that can be collected.

        :param host: Host where the artifacts are being collected.
        :type host: MultihostHost
        :param artifacts_type: Type of artifacts that are being collected.
        :type artifacts_type: MultihostArtifactsType
        :return: List of artifacts to collect.
        :rtype: set[str]
        """
        test_start = self.host.test_start_timestamp

        self.host.conn.run(f"journalctl --since @{test_start} > /var/log/journald.log")
        return {"/var/log/journald.log"}

    def clear(self) -> None:
        """
        Reset the journal window used by :meth:`journalctl` to the current time.
        """
        self._cursor = self.now

    def journalctl(
        self,
        current: bool = True,
        *,
        unit: str | None = None,
        lines: int | None = None,
        since: str | None = None,
        reverse: bool = False,
        grep: str | None = None,
        output: str | None = None,
        identifier: str | None = None,
        system: bool = False,
        user: bool = False,
        args: list[Any] | None = None,
    ) -> ProcessResult:
        """
        Execute journalctl with given arguments. Show messages only for current test run, by default.
        Note that raise_on_error is False and the command may return non-zero return code.

        When a ``--since @epoch`` bound is applied (the default for current-test
        queries):

        * matching is done in Python (``journalctl --grep`` can return hits from
          outside the ``--since`` window on some systemd versions);
        * output defaults to ``short-unix`` so entries older than the bound can
          be dropped in Python (``journalctl --since`` can still return older
          lines when the host clock has jumped).

        :param current: Show messages only for current test run, defaults to True
        :type current: bool, optional
        :param unit: Show messages for the specified systemd unit, defaults to None
        :type unit: str | None, optional
        :param lines: Show the most recent journal events and limit the number of events shown, defaults to None
        :type lines: int | None, optional
        :param since: Start showing entries on or newer than the specified date, defaults to None
        :type since: str | None, optional
        :param reverse: Reverse output so that the newest entries are displayed first, defaults to False
        :type reverse: bool, optional
        :param grep: Filter output to entries where the MESSAGE= field matches specified regex, defaults to None
        :type grep: str | None, optional
        :param output: Controls the formatting of the journal entries, defaults to None
        :type output: str | None, optional
        :param identifier: Show messages for the specified syslog identifier SYSLOG_IDENTIFIER, defaults to None
        :type identifier: str | None, optional
        :param system: Show messages from system services and the kernel, defaults to False
        :type system: bool, optional
        :param user: Show messages from service of current user, defaults to False
        :type user: bool, optional
        :param args: Additional options, defaults to None
        :type args: list[Any] | None, optional
        :return: SSH process result
        :rtype: ProcessResult
        """
        cli: CLIBuilder = self.host.cli
        window_start = self._cursor if self._cursor is not None else self.host.test_start_timestamp

        if current:
            since = since if since else f"@{window_start}"

        args = args if args else []
        enforce_since = self._parse_since_epoch(since)
        # Prefer client-side grep whenever a time bound is applied.
        native_grep = grep if (grep is not None and since is None) else None
        client_grep = grep if (grep is not None and since is not None) else None
        # short-unix lets us drop entries older than the bound when --since leaks.
        if enforce_since is not None and output is None:
            output = "short-unix"

        builder: CLIBuilderArgs = {
            "unit": (cli.option.VALUE, unit),
            "lines": (cli.option.VALUE, lines),
            "since": (cli.option.VALUE, since),
            "reverse": (cli.option.SWITCH, reverse),
            "grep": (cli.option.VALUE, native_grep),
            "output": (cli.option.VALUE, output),
            "identifier": (cli.option.VALUE, identifier),
            "system": (cli.option.SWITCH, system),
            "user": (cli.option.SWITCH, user),
            "no-pager": (cli.option.SWITCH, True),
        }

        result = self.host.conn.exec(["journalctl"] + cli.args(builder) + args, raise_on_error=False)

        lines_out = result.stdout_lines
        if enforce_since is not None:
            lines_out = self._filter_since(lines_out, enforce_since)
        if client_grep is not None:
            lines_out = [line for line in lines_out if self._line_matches(client_grep, line)]

        if lines_out is not result.stdout_lines:
            result.stdout_lines = lines_out
            result.stdout = "\n".join(lines_out)

        return result

    def is_match(self, pattern: str, unit: str | None = None) -> bool:
        """
        Search the logs for a pattern.

        Matching uses journal output bounded by the current test cursor and is
        evaluated in Python. This avoids two ``journalctl --grep`` pitfalls:
        matches from outside the ``--since`` window, and exit status 0 with
        ``-- No entries --`` (which previously made negative asserts fail).

        :param pattern: Pattern to be searched for
        :type pattern: str
        :param unit: Search only messages for given systemd unit, defaults to None
        :type unit: str | None, optional
        :return: True, if pattern found
        :rtype: bool
        """
        # Do not pass grep to journalctl; filter locally over the --since window.
        result = self.journalctl(unit=unit)
        return any(self._line_matches(pattern, line) for line in result.stdout_lines)

    def count(self, pattern: str, unit: str | None = None) -> int:
        """
        Search the logs for a pattern and return number of occurrences.

        :param pattern: Pattern to be searched for
        :type pattern: str
        :param unit: Search only messages for given systemd unit, defaults to None
        :type unit: str | None, optional
        :return: Number of occurrences of the pattern
        :rtype: int
        """
        result = self.journalctl(unit=unit)
        return sum(1 for line in result.stdout_lines if self._line_matches(pattern, line))

    @staticmethod
    def _parse_since_epoch(since: str | None) -> int | None:
        if since is None or not since.startswith("@"):
            return None
        try:
            return int(float(since[1:]))
        except ValueError:
            return None

    @staticmethod
    def _parse_short_unix_ts(line: str) -> int | None:
        """Parse leading seconds from ``journalctl -o short-unix`` output."""
        match = re.match(r"^(\d+)(?:\.\d+)?\s+", line)
        return int(match.group(1)) if match else None

    @classmethod
    def _filter_since(cls, lines: list[str], since_epoch: int) -> list[str]:
        kept: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped == "-- No entries --":
                continue
            ts = cls._parse_short_unix_ts(line)
            if ts is not None and ts < since_epoch:
                continue
            kept.append(line)
        return kept

    @staticmethod
    def _line_matches(pattern: str, line: str) -> bool:
        stripped = line.strip()
        if not stripped or stripped == "-- No entries --":
            return False
        return re.search(pattern, line) is not None
