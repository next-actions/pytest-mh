from __future__ import annotations

from copy import deepcopy


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
