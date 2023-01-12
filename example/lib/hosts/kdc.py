from __future__ import annotations

from pytest_mh import MultihostHost
from pytest_mh.ssh import SSHPowerShellProcess

from ..config import ExampleMultihostDomain


class KDCHost(MultihostHost[ExampleMultihostDomain]):
    """
    Kerberos KDC server host object.

    Provides features specific to Kerberos KDC.

    .. note::

        Full backup and restore is supported.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.__backup_location: str | None = None
        """Backup file or folder location."""

    def pytest_setup(self) -> None:
        """
        Called once before execution of any tests.
        """
        super().setup()

        # Backup KDC data
        self.ssh.run('kdb5_util dump /tmp/mh.kdc.kdb.backup && rm -f "/tmp/mh.kdc.kdb.backup.dump_ok"')
        self.__backup_location = "/tmp/mh.kdc.kdb.backup"

    def pytest_teardown(self) -> None:
        """
        Called once after all tests are finished.
        """
        # Remove backup file
        if self.__backup_location is not None:
            if self.ssh.shell is SSHPowerShellProcess:
                self.ssh.exec(["Remove-Item", "-Force", "-Recurse", self.__backup_location])
            else:
                self.ssh.exec(["rm", "-fr", self.__backup_location])

        super().teardown()

    def teardown(self) -> None:
        """
        Called after execution of each test.
        """
        # Restore KDC data to its original state
        self.ssh.run(f'kdb5_util load "{self.__backup_location}"')
        super().teardown()
