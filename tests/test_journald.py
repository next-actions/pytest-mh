from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from pytest_mh.cli import CLIBuilder
from pytest_mh.conn import Bash, ProcessResult
from pytest_mh.utils.journald import JournaldUtils


MATCH_LINE = "service: alert pattern is present in this line"
OTHER_LINE = "service: unrelated log line"


def _result(stdout_lines: list[str], rc: int = 0) -> ProcessResult:
    return ProcessResult(rc, stdout_lines, [], None)


@pytest.fixture
def journald(mocker: MockerFixture) -> JournaldUtils:
    host = mocker.MagicMock()
    host.cli = CLIBuilder(Bash())
    # Non-empty test start enables the --since / client-side grep path.
    host.test_start_timestamp = 1000
    host.conn.exec.return_value = _result([])
    return JournaldUtils(host)


def test_line_matches_ignores_empty_and_no_entries() -> None:
    assert JournaldUtils._line_matches("alert", "") is False
    assert JournaldUtils._line_matches("alert", "   ") is False
    assert JournaldUtils._line_matches("alert", "-- No entries --") is False


def test_line_matches_regex() -> None:
    assert JournaldUtils._line_matches(r"alert pattern", MATCH_LINE) is True
    assert JournaldUtils._line_matches(r"alert pattern.*this line", MATCH_LINE) is True
    assert JournaldUtils._line_matches(r"different pattern", MATCH_LINE) is False


def test_is_match_false_on_no_entries(journald: JournaldUtils, mocker: MockerFixture) -> None:
    """journalctl exits 0 with '-- No entries --'; that must not count as a match."""
    mocker.patch.object(journald, "journalctl", return_value=_result(["-- No entries --"], rc=0))

    assert journald.is_match(r"alert pattern", unit="sssd") is False


def test_is_match_true_when_pattern_present(journald: JournaldUtils, mocker: MockerFixture) -> None:
    mocker.patch.object(journald, "journalctl", return_value=_result([OTHER_LINE, MATCH_LINE]))

    assert journald.is_match(r"alert pattern", unit="sssd") is True


def test_is_match_false_when_pattern_absent(journald: JournaldUtils, mocker: MockerFixture) -> None:
    mocker.patch.object(journald, "journalctl", return_value=_result([OTHER_LINE]))

    assert journald.is_match(r"alert pattern", unit="sssd") is False


def test_count_matches_lines(journald: JournaldUtils, mocker: MockerFixture) -> None:
    mocker.patch.object(
        journald,
        "journalctl",
        return_value=_result([MATCH_LINE, OTHER_LINE, MATCH_LINE, "-- No entries --"]),
    )

    assert journald.count(r"alert pattern") == 2


def test_journalctl_filters_grep_in_python_when_since_set(
    journald: JournaldUtils,
) -> None:
    """With a --since bound, grep must not rely on journalctl --grep."""
    journald.host.conn.exec.return_value = _result([OTHER_LINE, MATCH_LINE, "-- No entries --"])

    result = journald.journalctl(grep=r"alert pattern", unit="sssd")

    argv = journald.host.conn.exec.call_args.args[0]
    assert "--grep" not in argv
    assert "--since" in argv
    assert result.stdout_lines == [MATCH_LINE]
    assert "alert pattern" in result.stdout
