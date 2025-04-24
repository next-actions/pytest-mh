"""SELinux utilities."""

from __future__ import annotations

import re

from .. import MultihostHost, MultihostUtility
from ..conn import ProcessLogLevel

__all__ = [
    "SELinuxContext",
    "SELinux",
]


class SELinuxContext(object):
    """
    Result of ``ls -Z``
    """

    def __init__(self, user: str, role: str, type: str, sensitivity: str, categories: str | None) -> None:
        self.user: str = user
        """
        SELinux user.
        """

        self.role: str = role
        """
        SELinux role.
        """

        self.type: str = type
        """
        SELinux type.
        """

        self.sensitivity: str = sensitivity
        """
        SELinux sensitivity level.
        """

        self.categories: str | None = categories
        """
        SELinux categories.
        """

    def __str__(self) -> str:
        return f"({self.user}:{self.role}:{self.type}:{self.sensitivity}:{self.categories})"

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other) -> bool:
        if not isinstance(other, SELinuxContext):
            return False

        return (
            self.user == other.user
            and self.role == other.role
            and self.type == other.type
            and self.sensitivity == other.sensitivity
            and self.categories == other.categories
        )

    @classmethod
    def FromOutput(cls, stdout: str) -> SELinuxContext:
        match = re.match(r"([^ ]+)\s+", stdout)

        if not match:
            raise ValueError("Unexpected value: expecting space separated string")

        selinux_context = match.group(1)
        labels = selinux_context.split(":")

        if len(labels) == 5:
            return cls(labels[0], labels[1], labels[2], labels[3], labels[4])
        elif len(labels) == 4:
            return cls(labels[0], labels[1], labels[2], labels[3], None)
        else:
            raise ValueError(f"Unexpected value: got {len(labels)} labels, expecting 4 or 5")


class SELinux(MultihostUtility[MultihostHost]):
    """
    SELinux utilities
    """

    def get_file_context(self, path: str) -> SELinuxContext | None:
        """
        Gets SELinux file context.

        :param path: File path.
        :type path: str
        :return: SELinux file context
        :rtype: SELinuxContext or None
        """
        self.logger.info(f'Getting SELinux context for "{path}"')
        result = self.host.conn.exec(["ls", "-Z", path], log_level=ProcessLogLevel.Error, raise_on_error=False)

        if result.rc != 0:
            return None

        return SELinuxContext.FromOutput(result.stdout)
