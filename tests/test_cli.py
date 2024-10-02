from __future__ import annotations

import pytest

from pytest_mh.cli import CLIBuilder
from pytest_mh.conn import Bash, Powershell


@pytest.mark.parametrize(
    "args, expected",
    [
        ({"arg": (CLIBuilder.option.VALUE, None)}, ""),
        ({"arg": (CLIBuilder.option.PLAIN, "value")}, "--arg value"),
        ({"arg": (CLIBuilder.option.PLAIN, "'value'")}, "--arg 'value'"),
        ({"arg": (CLIBuilder.option.PLAIN, '"value"')}, '--arg "value"'),
        ({"arg": (CLIBuilder.option.VALUE, "value")}, "--arg 'value'"),
        ({"arg": (CLIBuilder.option.SWITCH, False)}, ""),
        ({"arg": (CLIBuilder.option.SWITCH, True)}, "--arg"),
        ({"arg": (CLIBuilder.option.POSITIONAL, "value")}, "'value'"),
    ],
    ids=[
        "none",
        "plain-no-quotes",
        "plain-single-quotes",
        "plain-double-quotes",
        "value",
        "switch-false",
        "switch-true",
        "positional",
    ],
)
def test_cli__bash__CLIBuilder__command(args, expected):
    cli = CLIBuilder(Bash())
    line = cli.command("/bin/test", args)

    assert line == f"/bin/test {expected}".strip()


@pytest.mark.parametrize(
    "args, expected",
    [
        ({"arg": (CLIBuilder.option.VALUE, None)}, [None]),
        ({"arg": (CLIBuilder.option.PLAIN, "value")}, ["--arg", "value"]),
        ({"arg": (CLIBuilder.option.PLAIN, "'value'")}, ["--arg", "'value'"]),
        ({"arg": (CLIBuilder.option.PLAIN, '"value"')}, ["--arg", '"value"']),
        ({"arg": (CLIBuilder.option.VALUE, "value")}, ["--arg", "value"]),
        ({"arg": (CLIBuilder.option.SWITCH, False)}, [None]),
        ({"arg": (CLIBuilder.option.SWITCH, True)}, ["--arg"]),
        ({"arg": (CLIBuilder.option.POSITIONAL, "value")}, ["value"]),
    ],
    ids=[
        "none",
        "plain-no-quotes",
        "plain-single-quotes",
        "plain-double-quotes",
        "value",
        "switch-false",
        "switch-true",
        "positional",
    ],
)
def test_cli__bash__CLIBuilder__argv(args, expected):
    cli = CLIBuilder(Bash())
    argv = cli.argv("/bin/test", args)

    assert argv == ["/bin/test", *[x for x in expected if x is not None]]


@pytest.mark.parametrize(
    "args, quote_value, expected",
    [
        # quote_value=False
        ({"arg": (CLIBuilder.option.VALUE, None)}, False, [None]),
        ({"arg": (CLIBuilder.option.PLAIN, "value")}, False, ["--arg", "value"]),
        ({"arg": (CLIBuilder.option.PLAIN, "'value'")}, False, ["--arg", "'value'"]),
        ({"arg": (CLIBuilder.option.PLAIN, '"value"')}, False, ["--arg", '"value"']),
        ({"arg": (CLIBuilder.option.VALUE, "value")}, False, ["--arg", "value"]),
        ({"arg": (CLIBuilder.option.SWITCH, False)}, False, [None]),
        ({"arg": (CLIBuilder.option.SWITCH, True)}, False, ["--arg"]),
        ({"arg": (CLIBuilder.option.POSITIONAL, "value")}, False, ["value"]),
        # quote_value=True
        ({"arg": (CLIBuilder.option.VALUE, None)}, True, [None]),
        ({"arg": (CLIBuilder.option.PLAIN, "value")}, True, ["--arg", "value"]),
        ({"arg": (CLIBuilder.option.PLAIN, "'value'")}, True, ["--arg", "'value'"]),
        ({"arg": (CLIBuilder.option.PLAIN, '"value"')}, True, ["--arg", '"value"']),
        ({"arg": (CLIBuilder.option.VALUE, "value")}, True, ["--arg", "'value'"]),
        ({"arg": (CLIBuilder.option.SWITCH, False)}, True, [None]),
        ({"arg": (CLIBuilder.option.SWITCH, True)}, True, ["--arg"]),
        ({"arg": (CLIBuilder.option.POSITIONAL, "value")}, True, ["'value'"]),
    ],
    ids=[
        "unquoted-none",
        "unquoted-plain-no-quotes",
        "unquoted-plain-single-quotes",
        "unquoted-plain-double-quotes",
        "unquoted-value",
        "unquoted-switch-false",
        "unquoted-switch-true",
        "unquoted-positional",
        "quoted-none",
        "quoted-plain-no-quotes",
        "quoted-plain-single-quotes",
        "quoted-plain-double-quotes",
        "quoted-value",
        "quoted-switch-false",
        "quoted-switch-true",
        "quoted-positional",
    ],
)
def test_cli__bash__CLIBuilder__args(args, quote_value, expected):
    cli = CLIBuilder(Bash())
    args = cli.args(args, quote_value=quote_value)

    assert args == [x for x in expected if x is not None]


@pytest.mark.parametrize(
    "args, expected",
    [
        ({"arg": (CLIBuilder.option.VALUE, None)}, ""),
        ({"arg": (CLIBuilder.option.PLAIN, "value")}, "-arg value"),
        ({"arg": (CLIBuilder.option.PLAIN, "'value'")}, "-arg 'value'"),
        ({"arg": (CLIBuilder.option.PLAIN, '"value"')}, '-arg "value"'),
        ({"arg": (CLIBuilder.option.VALUE, "value")}, "-arg 'value'"),
        ({"arg": (CLIBuilder.option.SWITCH, False)}, "-arg:$False"),
        ({"arg": (CLIBuilder.option.SWITCH, True)}, "-arg:$True"),
        ({"arg": (CLIBuilder.option.POSITIONAL, "value")}, "'value'"),
    ],
    ids=[
        "none",
        "plain-no-quotes",
        "plain-single-quotes",
        "plain-double-quotes",
        "value",
        "switch-false",
        "switch-true",
        "positional",
    ],
)
def test_cli__powershell__CLIBuilder__command(args, expected):
    cli = CLIBuilder(Powershell())
    line = cli.command("/bin/test", args)

    assert line == f"/bin/test {expected}".strip()


@pytest.mark.parametrize(
    "args, expected",
    [
        ({"arg": (CLIBuilder.option.VALUE, None)}, [None]),
        ({"arg": (CLIBuilder.option.PLAIN, "value")}, ["-arg", "value"]),
        ({"arg": (CLIBuilder.option.PLAIN, "'value'")}, ["-arg", "'value'"]),
        ({"arg": (CLIBuilder.option.PLAIN, '"value"')}, ["-arg", '"value"']),
        ({"arg": (CLIBuilder.option.VALUE, "value")}, ["-arg", "value"]),
        ({"arg": (CLIBuilder.option.SWITCH, False)}, ["-arg:$False"]),
        ({"arg": (CLIBuilder.option.SWITCH, True)}, ["-arg:$True"]),
        ({"arg": (CLIBuilder.option.POSITIONAL, "value")}, ["value"]),
    ],
    ids=[
        "none",
        "plain-no-quotes",
        "plain-single-quotes",
        "plain-double-quotes",
        "value",
        "switch-false",
        "switch-true",
        "positional",
    ],
)
def test_cli__powershell__CLIBuilder__argv(args, expected):
    cli = CLIBuilder(Powershell())
    argv = cli.argv("/bin/test", args)

    assert argv == ["/bin/test", *[x for x in expected if x is not None]]


@pytest.mark.parametrize(
    "args, quote_value, expected",
    [
        # quote_value=False
        ({"arg": (CLIBuilder.option.VALUE, None)}, False, [None]),
        ({"arg": (CLIBuilder.option.PLAIN, "value")}, False, ["-arg", "value"]),
        ({"arg": (CLIBuilder.option.PLAIN, "'value'")}, False, ["-arg", "'value'"]),
        ({"arg": (CLIBuilder.option.PLAIN, '"value"')}, False, ["-arg", '"value"']),
        ({"arg": (CLIBuilder.option.VALUE, "value")}, False, ["-arg", "value"]),
        ({"arg": (CLIBuilder.option.SWITCH, False)}, False, ["-arg:$False"]),
        ({"arg": (CLIBuilder.option.SWITCH, True)}, False, ["-arg:$True"]),
        ({"arg": (CLIBuilder.option.POSITIONAL, "value")}, False, ["value"]),
        # quote_value=True
        ({"arg": (CLIBuilder.option.VALUE, None)}, True, [None]),
        ({"arg": (CLIBuilder.option.PLAIN, "value")}, True, ["-arg", "value"]),
        ({"arg": (CLIBuilder.option.PLAIN, "'value'")}, True, ["-arg", "'value'"]),
        ({"arg": (CLIBuilder.option.PLAIN, '"value"')}, True, ["-arg", '"value"']),
        ({"arg": (CLIBuilder.option.VALUE, "value")}, True, ["-arg", "'value'"]),
        ({"arg": (CLIBuilder.option.SWITCH, False)}, True, ["-arg:$False"]),
        ({"arg": (CLIBuilder.option.SWITCH, True)}, True, ["-arg:$True"]),
        ({"arg": (CLIBuilder.option.POSITIONAL, "value")}, True, ["'value'"]),
    ],
    ids=[
        "unquoted-none",
        "unquoted-plain-no-quotes",
        "unquoted-plain-single-quotes",
        "unquoted-plain-double-quotes",
        "unquoted-value",
        "unquoted-switch-false",
        "unquoted-switch-true",
        "unquoted-positional",
        "quoted-none",
        "quoted-plain-no-quotes",
        "quoted-plain-single-quotes",
        "quoted-plain-double-quotes",
        "quoted-value",
        "quoted-switch-false",
        "quoted-switch-true",
        "quoted-positional",
    ],
)
def test_cli__powershell__CLIBuilder__args(args, quote_value, expected):
    cli = CLIBuilder(Powershell())
    args = cli.args(args, quote_value=quote_value)

    assert args == [x for x in expected if x is not None]
