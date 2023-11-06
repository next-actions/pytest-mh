from __future__ import annotations

from typing import Any

from pytest_mh.cli import CLIBuilder, CLIBuilderArgs

from .. import MultihostHost, MultihostUtility
from ..ssh import SSHLog, SSHProcessResult

__all__ = ["JournaldUtils"]


class JournaldUtils(MultihostUtility):
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

    def setup(self) -> None:
        """
        Called before execution of each test.
        """
        self.clear()

    def clear(self) -> None:
        """
        Reset timestamp
        """
        self._test_start = self.host.ssh.exec(["date", "--rfc-3339=ns"], log_level=SSHLog.Error).stdout[0:19]

    def journalctl(
        self,
        current: bool = True,
        *,
        unit: str | None = None,
        lines: int | None = None,
        since: str | None = None,
        reverse: bool = False,
        no_pager: bool = False,
        grep: str | None = None,
        output: str | None = None,
        identifier: str | None = None,
        system: bool = False,
        user: bool = False,
        args: list[Any] | None = None,
    ) -> SSHProcessResult:
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
        :param no_pager: Do not pipe output into a pager, defaults to False
        :type no_pager: bool, optional
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
        :rtype: SSHProcessResult
        """
        cli: CLIBuilder = CLIBuilder(self.host.ssh)
        if current:
            since = since if since else self._test_start

        args = args if args else []
        builder: CLIBuilderArgs = {
            "unit": (cli.option.VALUE, unit),
            "lines": (cli.option.VALUE, lines),
            "since": (cli.option.VALUE, since),
            "reverse": (cli.option.SWITCH, reverse),
            "no-pager": (cli.option.SWITCH, no_pager),
            "grep": (cli.option.VALUE, grep),
            "output": (cli.option.VALUE, output),
            "identifier": (cli.option.VALUE, identifier),
            "system": (cli.option.SWITCH, system),
            "user": (cli.option.SWITCH, user),
        }

        return self.host.ssh.exec(["journalctl"] + cli.args(builder) + args, raise_on_error=False)

    def is_match(self, pattern: str) -> bool:
        """
        Search the logs for a pattern.

        :param pattern: Pattern to be searched for
        :type pattern: str
        :return: True, if pattern found
        :rtype: bool
        """
        return self.journalctl(grep=pattern).rc == 0

    def count(self, pattern: str) -> int:
        """
        Search the logs for a pattern and return number of occurrences.

        :param pattern: Pattern to be searched for
        :type pattern: str
        :return: Number of occurrences of the pattern
        :rtype: int
        """
        process = self.journalctl(grep=pattern)
        return len(process.stdout_lines) if process.rc == 0 else 0
