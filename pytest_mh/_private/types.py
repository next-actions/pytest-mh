from __future__ import annotations

from enum import Enum
from typing import Literal, TypeAlias


class MultihostOSFamily(Enum):
    """
    Host operating system family.
    """

    Linux = "linux"
    Windows = "windows"


MultihostOutcome: TypeAlias = Literal["passed", "failed", "skipped", "error", "unknown"]
