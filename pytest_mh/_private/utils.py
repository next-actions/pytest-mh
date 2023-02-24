from __future__ import annotations

from typing import Any


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

        return property in d and d[property]

    for key in required_keys:
        if not is_property_in_dict(key, confdict):
            raise ValueError(error_fmt.format(key=key))
