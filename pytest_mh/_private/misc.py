from __future__ import annotations

import signal
from collections.abc import Mapping
from copy import deepcopy
from functools import partial, wraps
from inspect import getfullargspec
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, ParamSpec, TypeVar

from .types import MultihostOutcome

if TYPE_CHECKING:
    from .artifacts import MultihostArtifactsMode


Param = ParamSpec("Param")
RetType = TypeVar("RetType")


def timeout(
    seconds: int, message: str = "Operation timed out"
) -> Callable[[Callable[Param, RetType]], Callable[Param, RetType]]:
    """
    Raise TimeoutError if function takes longer then ``seconds`` to finish.

    :param seconds: Number of seconds to wait.
    :type seconds: int
    :param message: Exception message, defaults to "Operation timed out"
    :type message: str, optional
    :raises ValueError: If ``seconds`` is less or equal to zero.
    :raises TimeoutError: If timeout occurrs.
    :return: Decorator.
    :rtype: Callable[[Callable[Param, RetType]], Callable[Param, RetType]]
    """
    if seconds < 0:
        raise ValueError(f"Invalid timeout value: {seconds}")

    def _timeout_handler(signum, frame):
        raise TimeoutError(seconds, message)

    def decorator(func: Callable[Param, RetType]) -> Callable[Param, RetType]:
        if seconds == 0:
            return func

        @wraps(func)
        def wrapper(*args: Param.args, **kwargs: Param.kwargs) -> RetType:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            old_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
            try:
                return func(*args, **kwargs)
            finally:
                signal.setitimer(signal.ITIMER_REAL, *old_timer)
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper

    return decorator


def validate_configuration(
    required_keys: list[str], confdict: dict[str, Any], error_fmt: str = '"{key}" property is missing'
) -> None:
    """
    Validate configuration dictionary.

    Check that it contains all required keys. The key may contain ``.`` to check
    nested keys, for example ``ssh.user``.

    :param required_keys: Required keys.
    :type required_keys: list[str]
    :param confdict: Configuration dictionary.
    :type confdict: dict[str, Any]
    :param error_fmt: _description_, defaults to '"{key}" property is missing'
    :type error_fmt: str, optional
    :raises ValueError: If a required key is missing or empty.
    :return: ``True`` if all keys are present and not empty, ``False`` otherwise.
    :rtype: bool
    """

    def is_property_in_dict(property: str, d: dict[str, Any]) -> bool:
        if "." in property:
            (key, subpath) = property.split(".", maxsplit=1)
            if not d.get(key, None):
                return False

            return is_property_in_dict(subpath, d[key])

        return isinstance(d, Mapping) and property in d and d[property]

    for key in required_keys:
        if not is_property_in_dict(key, confdict):
            raise ValueError(error_fmt.format(key=key))


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

    def clear(self, name: str) -> None:
        """
        Clear state of the operation.

        :param name: Operation name.
        :type name: str
        """
        if name in self.states:
            del self.states[name]

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
