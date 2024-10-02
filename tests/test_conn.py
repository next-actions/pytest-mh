from __future__ import annotations

import textwrap

import pytest

from pytest_mh.conn import Bash, Powershell


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
    assert shell.shell_command == "/usr/bin/bash -c"

    cmd = shell.build_command_line(input, cwd=None, env={})
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_bash__cwd():
    shell = Bash()

    assert shell.name == "bash"
    assert shell.shell_command == "/usr/bin/bash -c"

    cmd = shell.build_command_line("echo hello world", cwd="/home/test", env={})
    expected = textwrap.dedent(
        """
        cd /home/test

        echo hello world
        """
    ).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_bash__env():
    shell = Bash()

    assert shell.name == "bash"
    assert shell.shell_command == "/usr/bin/bash -c"

    cmd = shell.build_command_line("echo hello world", cwd=None, env={"HELLO": "WORLD", "JOHN": "DOE"})
    expected = textwrap.dedent(
        """
        export HELLO=WORLD
        export JOHN=DOE

        echo hello world
        """
    ).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_bash__cwd_env():
    shell = Bash()

    assert shell.name == "bash"
    assert shell.shell_command == "/usr/bin/bash -c"

    cmd = shell.build_command_line("echo hello world", cwd="/home/test", env={"HELLO": "WORLD", "JOHN": "DOE"})
    expected = textwrap.dedent(
        """
        export HELLO=WORLD
        export JOHN=DOE
        cd /home/test

        echo hello world
        """
    ).strip()
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
    expected = textwrap.dedent(
        """
        cd /home/test

        Write-Output hello world
        """
    ).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_powershell__env():
    shell = Powershell()

    assert shell.name == "powershell"
    assert shell.shell_command == "powershell -NonInteractive -Command"

    cmd = shell.build_command_line("Write-Output hello world", cwd=None, env={"HELLO": "WORLD", "JOHN": "DOE"})
    expected = textwrap.dedent(
        """
        $Env:HELLO = WORLD
        $Env:JOHN = DOE

        Write-Output hello world
        """
    ).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"


def test_conn__shell_powershell__cwd_env():
    shell = Powershell()

    assert shell.name == "powershell"
    assert shell.shell_command == "powershell -NonInteractive -Command"

    cmd = shell.build_command_line("echo hello world", cwd="/home/test", env={"HELLO": "WORLD", "JOHN": "DOE"})
    expected = textwrap.dedent(
        """
        $Env:HELLO = WORLD
        $Env:JOHN = DOE
        cd /home/test

        echo hello world
        """
    ).strip()
    assert cmd == f"{shell.shell_command} '{expected}'"
