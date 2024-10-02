from __future__ import annotations

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

        self._test_start: str = ""
        self._cursor: str = ""

    @property
    def now(self) -> str:
        """
        :return: Current date and time that can be used to filter the journal.
        :rtype: str
        """
        return self.host.conn.exec(["date", "+%Y-%m-%d %H:%M:%S.%N"], log_level=ProcessLogLevel.Error).stdout.strip()

    def setup(self) -> None:
        """
        Called before execution of each test.
        """
        self._test_start = self.now
        self._cursor = self._test_start

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
        self.host.conn.run(f"journalctl --since '{self._test_start}' > /var/log/journald.log")
        return {"/var/log/journald.log"}

    def clear(self) -> None:
        """
        Reset timestamp
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
        if current:
            since = since if since else self._cursor

        args = args if args else []
        builder: CLIBuilderArgs = {
            "unit": (cli.option.VALUE, unit),
            "lines": (cli.option.VALUE, lines),
            "since": (cli.option.VALUE, since),
            "reverse": (cli.option.SWITCH, reverse),
            "grep": (cli.option.VALUE, grep),
            "output": (cli.option.VALUE, output),
            "identifier": (cli.option.VALUE, identifier),
            "system": (cli.option.SWITCH, system),
            "user": (cli.option.SWITCH, user),
            "no-pager": (cli.option.SWITCH, True),
        }

        return self.host.conn.exec(["journalctl"] + cli.args(builder) + args, raise_on_error=False)

    def is_match(self, pattern: str, unit: str | None = None) -> bool:
        """
        Search the logs for a pattern.

        :param pattern: Pattern to be searched for
        :type pattern: str
        :param unit: Search only messages for given systemd unit, defaults to None
        :type unit: str | None, optional
        :return: True, if pattern found
        :rtype: bool
        """
        return self.journalctl(grep=pattern, unit=unit).rc == 0

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
        process = self.journalctl(grep=pattern, unit=unit)
        return len(process.stdout_lines) if process.rc == 0 else 0
