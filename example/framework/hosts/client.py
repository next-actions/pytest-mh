"""IPA multihost host."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from pytest_mh.conn import ProcessLogLevel

from .base import BaseHost

__all__ = [
    "ClientHost",
]


class ClientHost(BaseHost):
    """
    Sudo client host.

    Sudo tests are run on this machine.

    Implements backup and restore of sudo and SSSD.

    Expectations:

    * installed sudo
    * installed sssd
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def pytest_setup(self) -> None:
        super().pytest_setup()

        # SSSD is started only for selected tests by the topology controller.
        # Make sure it is stopped by default.
        self.svc.stop("sssd.service")

    def start(self) -> None:
        raise NotImplementedError("sudo is not a service")

    def stop(self) -> None:
        raise NotImplementedError("sudo is not a service")

    def backup(self) -> Any:
        """
        Backup sudoers.

        :return: Backup data.
        :rtype: Any
        """
        self.logger.info("Creating backup of sudo client")

        # sudo
        self.fs.backup("/etc/sudo.conf")
        self.fs.backup("/etc/sudoers")
        self.fs.backup("/etc/sudoers.d")

        # SSSD
        self.fs.backup("/etc/sssd")
        self.fs.backup("/var/lib/sss")
        self.fs.backup("/var/log/sssd")

        result = self.conn.run(
            """
            set -ex

            function backup {
                if [ -d "$1" ] || [ -f "$1" ]; then
                    cp --force --archive "$1" "$2"
                fi
            }

            path=`mktemp -d`
            backup /etc/sudo.conf "$path/sudo.conf"
            backup /etc/sudoers "$path/sudoers"
            backup /etc/sudoers.d "$path/sudoers.d"
            backup /etc/sssd "$path/sssd"
            backup /var/log/sssd "$path/sssd-logs"
            backup /var/lib/sss "$path/sssd-lib"

            echo $path
            """,
            log_level=ProcessLogLevel.Error,
        )

        return PurePosixPath(result.stdout_lines[-1].strip())

    def restore(self, backup_data: Any | None) -> None:
        """
        Restore sudoers.

        :param backup_data: Backup data.
        :type backup_data: PurePath | Sequence[PurePath] | Any | None
        """
        # This would have been called automatically by the utility,
        # therefore there is no need for these calls. However, it is
        # good to call it explicitly for clarity.
        self.logger.info("Restoring sudo client from backup")

        # sudo
        self.fs.restore("/etc/sudo.conf")
        self.fs.restore("/etc/sudoers")
        self.fs.restore("/etc/sudoers.d")

        # SSSD
        self.fs.restore("/etc/sssd")
        self.fs.restore("/var/lib/sss")
        self.fs.restore("/var/log/sssd")

        if backup_data is None:
            return

        if not isinstance(backup_data, PurePosixPath):
            raise TypeError(f"Expected PurePosixPath, got {type(backup_data)}")

        backup_path = str(backup_data)

        self.logger.info(f"Restoring client data from {backup_path}")
        self.conn.run(
            f"""
            set -ex

            function restore {{
                rm --force --recursive "$2"
                if [ -d "$1" ] || [ -f "$1" ]; then
                    cp --force --archive "$1" "$2"
                fi
            }}

            rm --force --recursive /etc/sudo.conf /etc/sudoers /etc/sudoers.d /etc/sssd /var/lib/sss /var/log/sssd
            restore "{backup_path}/sudo.conf" /etc/sudo.conf
            restore "{backup_path}/sudoers" /etc/sudoers
            restore "{backup_path}/sudoers.d" /etc/sudoers.d
            restore "{backup_path}/sssd" /etc/sssd
            restore "{backup_path}/sssd-logs" /var/log/sssd
            restore "{backup_path}/sssd-lib" /var/lib/sss
            """,
            log_level=ProcessLogLevel.Error,
        )
