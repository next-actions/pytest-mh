from __future__ import annotations

from copy import deepcopy
from functools import partial
from inspect import getfullargspec
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .types import MultihostOutcome

if TYPE_CHECKING:
    from .artifacts import MultihostArtifactsMode


def merge_dict(*args: dict | None):
    """
    Merge two or more nested dictionaries together.

    Nested dictionaries are not overwritten but combined.
    """
    filtered_args = [x for x in args if x is not None]
    if not filtered_args:
        return {}

    dest = deepcopy(filtered_args[0])

    for source in filtered_args[1:]:
        for key, value in source.items():
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


def sanitize_path(path: str | Path) -> Path:
    """
    Replace problematic characters in file path.

    :param path: Path to sanitize.
    :type path: str | Path
    :return: Sanitized path.
    :rtype: Path
    """
    table = str.maketrans('":<>|*? [', "---------", "]()")
    return Path(str(path).translate(table))


def should_collect_artifacts(mode: MultihostArtifactsMode, outcome: MultihostOutcome) -> bool:
    """
    Match mode and outcome in order to decide if artifacts should be
    collected/written or not.

    :param mode: Artifacts collect mode.
    :type mode: MultihostArtifactsMode
    :param outcome: Test or operation outcome.
    :type outcome: MultihostOutcome
    :raises ValueError: If mode is not recognized.
    :return: True if artifacts should be collected, False otherwise.
    :rtype: bool
    """
    match mode:
        case "never":
            return False
        case "always":
            return True
        case "on-failure":
            return outcome in ("failed", "error", "unknown")

    raise ValueError(f"Unexpected artifacts collection mode: {mode}")


class OperationStatus(object):
    """
    Keep named states of operation.

    This can be used to mark certain operations as completed with success,
    failure or any other state and act later upon it.
    """

    def __init__(self) -> None:
        self.states: dict[str, str] = {}

    def set(self, name: str, state: str) -> None:
        """
        Set current state of the operation.

        :param name: Operation name.
        :type name: str
        :param state: Current state.
        :type state: str
        """
        self.states[name] = state

    def set_success(self, name: str) -> None:
        """
        Mark operation as successful.

        :param name: Operation name.
        :type name: str
        """
        self.set(name, "success")

    def set_failure(self, name: str) -> None:
        """
        Mark operation as failed.

        :param name: Operation name.
        :type name: str
        """
        self.set(name, "failure")

    def check(self, name: str, expected_state: str) -> bool:
        """
        Check operation state.

        :param name: Operation name.
        :type name: str
        :param expected_state: Expected state.
        :type expected_state: str
        :return: True if current state equals to the expected state, False otherwise.
        :rtype: bool
        """
        state = self.states.get(name, None)
        if state is None:
            return False

        return state == expected_state

    def check_success(self, name: str) -> bool:
        """
        Check if operation state is success.

        :param name: Operation name.
        :type name: str
        :return: True if current state equals to ``success``, False otherwise.
        :rtype: bool
        """
        return self.check(name, "success")

    def check_failure(self, name: str) -> bool:
        """
        Check if operation state is failure.

        :param name: Operation name.
        :type name: str
        :return: True if current state equals to ``failure``, False otherwise.
        :rtype: bool
        """
        return self.check(name, "failure")
