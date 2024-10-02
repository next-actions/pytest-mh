from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from pytest_mh._private.misc import (
    OperationStatus,
    invoke_callback,
    merge_dict,
    sanitize_path,
    should_collect_artifacts,
    validate_configuration,
)


@pytest.mark.parametrize(
    "required_keys, confdict, match_key",
    [
        (["key_a"], {"key_a": True}, None),
        (["key_a"], {"key_b": True}, "key_a"),
        (["key_a.key_a_a"], {"key_a": True, "key_b": True}, "key_a.key_a_a"),
        (["key_a.key_a_a"], {"key_a": {"key_a_a": True}, "key_b": True}, None),
    ],
    ids=[
        "root-present",
        "root-missing",
        "nested-missing",
        "nested-ok",
    ],
)
def test_misc__validate_configuration(required_keys, confdict, match_key):
    if match_key is None:
        validate_configuration(required_keys, confdict)
        return

    # default error message
    with pytest.raises(ValueError, match=f'"{match_key}" property is missing'):
        validate_configuration(required_keys, confdict)

    # custom error message
    with pytest.raises(ValueError, match=f"custom message {match_key}"):
        validate_configuration(required_keys, confdict, error_fmt="custom message {key}")


@pytest.mark.parametrize(
    "dicts, expected",
    [
        ([None], dict()),
        ([dict()], dict()),
        ([None, None], dict()),
        ([dict(), dict()], dict()),
        ([dict(), dict(), dict()], dict()),
        ([None, dict(a="a", b="b")], dict(a="a", b="b")),
        ([None, dict(a="a", b="b")], dict(a="a", b="b")),
        ([dict(a="a", b="b"), None], dict(a="a", b="b")),
        ([dict(), dict(a="a", b="b")], dict(a="a", b="b")),
        ([dict(a="a", b="b"), dict()], dict(a="a", b="b")),
        ([dict(a="a"), dict(b="b"), dict(c="c")], dict(a="a", b="b", c="c")),
        ([dict(a="a", b="b"), dict(c="c")], dict(a="a", b="b", c="c")),
        (
            [
                dict(a="a", b=dict(bb="bb")),
                dict(c="c"),
            ],
            dict(a="a", b=dict(bb="bb"), c="c"),
        ),
        (
            [
                dict(a="a", b=dict(bb="bb")),
                dict(b="b"),
            ],
            dict(a="a", b="b"),
        ),
        (
            [
                dict(a="a", b=dict(bb="bb")),
                dict(b=dict(bb="1")),
            ],
            dict(a="a", b=dict(bb="1")),
        ),
        (
            [
                dict(a="a", b=dict(bb="bb")),
                dict(b=dict(bc="bc")),
            ],
            dict(a="a", b=dict(bb="bb", bc="bc")),
        ),
        (
            [
                dict(a="a", b=dict(bb="bb")),
                dict(b=dict(bc="bc")),
                dict(b=dict(bd="bd")),
            ],
            dict(a="a", b=dict(bb="bb", bc="bc", bd="bd")),
        ),
        (
            [
                dict(a="a", b=dict(bb=dict(bbb="bbb"))),
                dict(b=dict(bc="bc")),
                dict(b=dict(bb=dict(bbc="bbc"))),
            ],
            dict(a="a", b=dict(bb=dict(bbb="bbb", bbc="bbc"), bc="bc")),
        ),
    ],
)
def test_misc__merge_dict(dicts, expected):
    result = merge_dict(*dicts)
    assert result == expected


def test_misc__invoke_callback__exact():
    def _cb(a, b, c) -> None:
        assert a == 1
        assert b == 2
        assert c == 3

    invoke_callback(_cb, a=1, b=2, c=3)
    invoke_callback(partial(_cb, 1), b=2, c=3)
    invoke_callback(partial(_cb, 1, 2), c=3)
    invoke_callback(partial(_cb, a=1), b=2, c=3)


def test_misc__invoke_callback__subset():
    def _cb(a, b, c) -> None:
        assert a == 1
        assert b == 2
        assert c == 3

    invoke_callback(_cb, a=1, b=2, c=3, d=4, e=5)
    invoke_callback(partial(_cb, 1), b=2, c=3, d=4, e=5)
    invoke_callback(partial(_cb, 1, 2), c=3, d=4, e=5)
    invoke_callback(partial(_cb, a=1), b=2, c=3, d=4, e=5)


def test_misc__invoke_callback__kwonly():
    def _cb(a, *, b, c) -> None:
        assert a == 1
        assert b == 2
        assert c == 3

    invoke_callback(_cb, a=1, b=2, c=3)
    invoke_callback(partial(_cb, 1), b=2, c=3)
    invoke_callback(partial(_cb, a=1), b=2, c=3)
    invoke_callback(partial(_cb, b=2), a=1, c=3)


def test_misc__invoke_callback__kwargs():
    def _cb(**kwargs) -> None:
        assert kwargs["a"] == 1
        assert kwargs["b"] == 2
        assert kwargs["c"] == 3

    invoke_callback(_cb, a=1, b=2, c=3)
    invoke_callback(partial(_cb, a=1), b=2, c=3)
    invoke_callback(partial(_cb, b=2), a=1, c=3)
    invoke_callback(partial(_cb, b=2, c=3), a=1)


def test_misc__invoke_callback__kwargs_mixed():
    def _cb(d, **kwargs) -> None:
        assert kwargs["a"] == 1
        assert kwargs["b"] == 2
        assert kwargs["c"] == 3
        assert d == 4

    invoke_callback(_cb, a=1, b=2, c=3, d=4)
    invoke_callback(partial(_cb, 4), a=1, b=2, c=3)
    invoke_callback(partial(_cb, a=1), b=2, c=3, d=4)
    invoke_callback(partial(_cb, d=4), a=1, b=2, c=3)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("hello", "hello"),
        ("hello/world", "hello/world"),
        ("/hello/world", "/hello/world"),
        ('hello/":<>|*? [', "hello/---------"),
        ("hello/]()world", "hello/world"),
        ("tests/test_foo.py::test_bar[a] (topology)", "tests/test_foo.py--test_bar-a-topology"),
    ],
)
def test_misc__sanitize_path(path, expected):
    expected = Path(expected)
    assert sanitize_path(path) == expected
    assert sanitize_path(Path(path)) == expected


@pytest.mark.parametrize(
    "mode, outcome, expected",
    [
        ("never", "success", False),
        ("never", "failed", False),
        ("never", "error", False),
        ("never", "unknown", False),
        ("always", "success", True),
        ("always", "failed", True),
        ("always", "error", True),
        ("always", "unknown", True),
        ("on-failure", "success", False),
        ("on-failure", "failed", True),
        ("on-failure", "error", True),
        ("on-failure", "unknown", True),
    ],
)
def test_misc__should_collect_artifacts(mode, outcome, expected):
    assert should_collect_artifacts(mode, outcome) == expected


def test_misc__should_collect_artifacts__invalid_mode():
    with pytest.raises(ValueError):
        should_collect_artifacts("invalid-mode", "success")


def test_misc__OperationStatus():
    op = OperationStatus()
    op.set("example", "in-progress")
    op.set_success("setup")
    op.set_failure("teardown")

    assert op.check("example", "in-progress")
    assert not op.check("example", "success")
    assert not op.check("missing", "success")

    assert op.check_success("setup")
    assert not op.check_success("teardown")

    assert op.check_failure("teardown")
    assert not op.check_failure("setup")

    op.clear("setup")
    assert not op.check_success("setup")
