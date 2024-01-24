from __future__ import annotations

from functools import partial

from pytest_mh._private.misc import invoke_callback


def test_invoke_callback__exact():
    def _cb(a, b, c) -> None:
        assert a == 1
        assert b == 2
        assert c == 3

    invoke_callback(_cb, a=1, b=2, c=3)
    invoke_callback(partial(_cb, 1), b=2, c=3)
    invoke_callback(partial(_cb, 1, 2), c=3)
    invoke_callback(partial(_cb, a=1), b=2, c=3)


def test_invoke_callback__subset():
    def _cb(a, b, c) -> None:
        assert a == 1
        assert b == 2
        assert c == 3

    invoke_callback(_cb, a=1, b=2, c=3, d=4, e=5)
    invoke_callback(partial(_cb, 1), b=2, c=3, d=4, e=5)
    invoke_callback(partial(_cb, 1, 2), c=3, d=4, e=5)
    invoke_callback(partial(_cb, a=1), b=2, c=3, d=4, e=5)


def test_invoke_callback__kwonly():
    def _cb(a, *, b, c) -> None:
        assert a == 1
        assert b == 2
        assert c == 3

    invoke_callback(_cb, a=1, b=2, c=3)
    invoke_callback(partial(_cb, 1), b=2, c=3)
    invoke_callback(partial(_cb, a=1), b=2, c=3)
    invoke_callback(partial(_cb, b=2), a=1, c=3)


def test_invoke_callback__kwargs():
    def _cb(**kwargs) -> None:
        assert kwargs["a"] == 1
        assert kwargs["b"] == 2
        assert kwargs["c"] == 3

    invoke_callback(_cb, a=1, b=2, c=3)
    invoke_callback(partial(_cb, a=1), b=2, c=3)
    invoke_callback(partial(_cb, b=2), a=1, c=3)
    invoke_callback(partial(_cb, b=2, c=3), a=1)


def test_invoke_callback__kwargs_mixed():
    def _cb(d, **kwargs) -> None:
        assert kwargs["a"] == 1
        assert kwargs["b"] == 2
        assert kwargs["c"] == 3
        assert d == 4

    invoke_callback(_cb, a=1, b=2, c=3, d=4)
    invoke_callback(partial(_cb, 4), a=1, b=2, c=3)
    invoke_callback(partial(_cb, a=1), b=2, c=3, d=4)
    invoke_callback(partial(_cb, d=4), a=1, b=2, c=3)
