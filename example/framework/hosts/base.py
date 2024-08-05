"""Base classes sudo testing."""

from __future__ import annotations

from pytest_mh import MultihostBackupHost
from pytest_mh.utils.fs import LinuxFileSystem
from pytest_mh.utils.services import SystemdServices

from ..config import SUDOMultihostDomain

__all__ = [
    "BaseHost",
]


class BaseHost(MultihostBackupHost[SUDOMultihostDomain]):
    """
    Base class for all hosts.

    Requires implementation of :class:`pytest_mh.MultihostBackupHost` interface
    and provides access to filesystem and systemd via :attr:`fs` and
    :attr:`svc`.
    """

    def __init__(self, *args, **kwargs) -> None:
        # Restore is handled in topology controllers
        super().__init__(*args, auto_restore=False, **kwargs)

        self.fs: LinuxFileSystem = LinuxFileSystem(self)
        self.svc: SystemdServices = SystemdServices(self)
