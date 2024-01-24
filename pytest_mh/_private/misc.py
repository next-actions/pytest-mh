from __future__ import annotations

from copy import deepcopy
from functools import partial
from inspect import getfullargspec
from typing import Any, Callable


def merge_dict(d1, d2):
    """
    Merge two nested dictionaries together.

    Nested dictionaries are not overwritten but combined.
    """
    dest = deepcopy(d1)
    for key, value in d2.items():
        if isinstance(value, dict):
            dest[key] = merge_dict(dest.get(key, {}), value)
            continue

        dest[key] = value

    return dest


def invoke_callback(cb: Callable, /, **kwargs: Any) -> Any:
    """
    Invoke callback with given arguments.

    The callback may take all or only selected subset of given arguments.

    :param cb: Callback to call.
    :type cb: Callable
    :param `*kwargs`: Callback parameters.
    :type `*kwargs`: dict[str, Any]
    :param
    :return: Return value of the callabck.
    :rtype: Any
    """
    cb_args: list[str] = []

    # Get list of parameters required by the callback
    if isinstance(cb, partial):
        spec = getfullargspec(cb.func)

        cb_args = spec.args + spec.kwonlyargs

        # Remove bound positional parameters
        cb_args = cb_args[len(cb.args) :]

        # Remove bound keyword parameters
        cb_args = [x for x in cb_args if x not in cb.keywords]
    else:
        spec = getfullargspec(cb)
        cb_args = spec.args + spec.kwonlyargs

    if spec.varkw is None:
        # No **kwargs is present, just pick selected arguments
        callspec = {k: v for k, v in kwargs.items() if k in cb_args}
    else:
        # **kwargs is present, pass everything
        callspec = kwargs

    return cb(**callspec)
