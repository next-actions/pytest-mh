from __future__ import annotations

import textwrap
from unittest.mock import MagicMock, patch

import pytest
from pylibsshext.errors import LibsshChannelException

from pytest_mh.conn import Bash, Powershell
from pytest_mh.conn.ssh import SSHClient


def _mock_logger() -> MagicMock:
    logger = MagicMock()
    logger.colorize.side_effect = lambda text, *colors: str(text)
    return logger


@patch("pytest_mh.conn.ssh.LibsshSession")
def test_ssh_client__open_channel_reconnects_once(SessionCls: MagicMock):
    """Dead session: first new_channel fails with LibsshChannelException; reconnect and retry."""
    session1 = MagicMock()
    session2 = MagicMock()
    SessionCls.side_effect = [session1, session2]

    channel = MagicMock()
    session1.is_connected = True
    session1.new_channel.side_effect = LibsshChannelException("Unable to open channel")
    session2.is_connected = False
    session2.new_channel.return_value = channel

    client = SSHClient(
        "host.example",
        user="root",
        password="secret",
        shell=Bash(),
        logger=_mock_logger(),
    )
    assert client.session is session1

    # pytest-multihost stubs SSHClient.connect to raise; replace with no-op for reconnect.
    with patch.object(SSHClient, "connect", MagicMock(return_value=None)) as mock_connect:
        assert client.open_channel() is channel
        mock_connect.assert_called_once()

    session1.disconnect.assert_called()
    session2.new_channel.assert_called_once()
    assert client.session is session2


@patch("pytest_mh.conn.ssh.LibsshSession")
def test_ssh_client__open_channel_no_reconnect_on_success(SessionCls: MagicMock):
    session = MagicMock()
    SessionCls.return_value = session
    channel = MagicMock()
    session.new_channel.return_value = channel

    client = SSHClient(
        "host.example",
        user="root",
        password="secret",
        shell=Bash(),
        logger=_mock_logger(),
    )

    assert client.open_channel() is channel
    session.new_channel.assert_called_once()
    SessionCls.assert_called_once()


@pytest.mark.parametrize(
    "input, expected",
    [
        ("echo hello world", "echo hello world"),
        ('echo "hello world"', 'echo "hello world"'),
        ("echo 'hello world'", "echo '\"'\"'hello world'\"'\"'"),
    ],
    ids=[
        "no-quotes",
        "double-quotes",
        "single-quotes",
    ],
)
def test_conn__shell_bash__script(input: str, expected: str):
    shell = Bash()

    assert shell.name == "bash"
    assert shell.shell_command == "/usr/bin/env bash -c"

    cmd = shell.build_command_line(input, cwd=None, env={})
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_bash__cwd():
    shell = Bash()

    assert shell.name == "bash"
    assert shell.shell_command == "/usr/bin/env bash -c"

    cmd = shell.build_command_line("echo hello world", cwd="/home/test", env={})
    expected = textwrap.dedent("""
        cd /home/test

        echo hello world
        """).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_bash__env():
    shell = Bash()

    assert shell.name == "bash"
    assert shell.shell_command == "/usr/bin/env bash -c"

    cmd = shell.build_command_line("echo hello world", cwd=None, env={"HELLO": "WORLD", "JOHN": "DOE"})
    expected = textwrap.dedent("""
        export HELLO=WORLD
        export JOHN=DOE

        echo hello world
        """).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_bash__cwd_env():
    shell = Bash()

    assert shell.name == "bash"
    assert shell.shell_command == "/usr/bin/env bash -c"

    cmd = shell.build_command_line("echo hello world", cwd="/home/test", env={"HELLO": "WORLD", "JOHN": "DOE"})
    expected = textwrap.dedent("""
        export HELLO=WORLD
        export JOHN=DOE
        cd /home/test

        echo hello world
        """).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"


@pytest.mark.parametrize(
    "input, expected",
    [
        ("Write-Output hello world", "Write-Output hello world"),
        ('Write-Output "hello world"', 'Write-Output \\"hello world\\"'),
        ("Write-Output 'hello world'", "Write-Output ''hello world''"),
    ],
    ids=[
        "no-quotes",
        "double-quotes",
        "single-quotes",
    ],
)
def test_conn__shell_powershell__script(input: str, expected: str):
    shell = Powershell()

    assert shell.name == "powershell"
    assert shell.shell_command == "powershell -NonInteractive -Command"

    cmd = shell.build_command_line(input, cwd=None, env={})
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_powershell__cwd():
    shell = Powershell()

    assert shell.name == "powershell"
    assert shell.shell_command == "powershell -NonInteractive -Command"

    cmd = shell.build_command_line("Write-Output hello world", cwd="/home/test", env={})
    expected = textwrap.dedent("""
        cd /home/test

        Write-Output hello world
        """).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_powershell__env():
    shell = Powershell()

    assert shell.name == "powershell"
    assert shell.shell_command == "powershell -NonInteractive -Command"

    cmd = shell.build_command_line("Write-Output hello world", cwd=None, env={"HELLO": "WORLD", "JOHN": "DOE"})
    expected = textwrap.dedent("""
        $Env:HELLO = WORLD
        $Env:JOHN = DOE

        Write-Output hello world
        """).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_powershell__cwd_env():
    shell = Powershell()

    assert shell.name == "powershell"
    assert shell.shell_command == "powershell -NonInteractive -Command"

    cmd = shell.build_command_line("echo hello world", cwd="/home/test", env={"HELLO": "WORLD", "JOHN": "DOE"})
    expected = textwrap.dedent("""
        $Env:HELLO = WORLD
        $Env:JOHN = DOE
        cd /home/test

        echo hello world
        """).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"
