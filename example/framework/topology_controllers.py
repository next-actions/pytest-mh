from __future__ import annotations

import re

from pytest_mh import BackupTopologyController

from .config import SUDOMultihostConfig
from .hosts.client import ClientHost
from .hosts.ldap import LDAPHost

__all__ = [
    "LDAPTopologyController",
    "SSSDTopologyController",
    "SudoersTopologyController",
]


class BaseTopologyController(BackupTopologyController[SUDOMultihostConfig]):
    def set_nsswitch(self, client: ClientHost, contents: dict[str, str]) -> None:
        """
        Set lines in nsswitch.conf.
        """
        self.logger.info(f"Setting 'nsswitch.conf:sudoers={contents}' on {client.hostname}")

        nsswitch = client.fs.read("/etc/nsswitch.conf")

        # remove any sudoers line
        for key in contents.keys():
            re.sub(rf"^{key}:.*$", "", nsswitch, flags=re.MULTILINE)

        # add new sudoers line
        nsswitch += "\n"
        for key, value in contents.items():
            nsswitch += f"{key}: {value}\n"

        # write the file, backup of the file is taken automatically
        client.fs.write("/etc/authselect/nsswitch.conf", nsswitch, dedent=False)

    def configure_sssd(self, client: ClientHost, ldap: LDAPHost) -> None:
        """
        Configure SSSD for identity.
        """
        client.fs.backup("/etc/authselect")
        client.conn.run("authselect select sssd --force --nobackup")

        # Configure SSSD
        client.fs.rm("/etc/sssd/conf.d")
        client.fs.write(
            "/etc/sssd/sssd.conf",
            f"""
            [sssd]
            debug_level = 0xfff0
            services = nss, pam, sudo
            domains = test

            [sudo]
            debug_level = 0xfff0

            [nss]
            debug_level = 0xfff0

            [pam]
            debug_level = 0xfff0

            [domain/test]
            debug_level = 0xfff0
            id_provider = ldap
            ldap_uri = ldap://{ldap.hostname}
            ldap_tls_reqcert = never
            """,
            mode="0600",
        )

        # Remove SSSD data to start fresh
        client.conn.run(
            """
            rm -fr /var/lib/sss/db/* /var/lib/sss/mc/* /var/log/sssd/*
            """
        )


class SudoersTopologyController(BaseTopologyController):
    @BackupTopologyController.restore_vanilla_on_error
    def topology_setup(self, client: ClientHost) -> None:
        # Set sudo to use sudoers as source
        self.set_nsswitch(client, {"sudoers": "files"})

        # Backup all hosts so we can restore to this state after each test
        super().topology_setup()


class LDAPTopologyController(BaseTopologyController):
    @BackupTopologyController.restore_vanilla_on_error
    def topology_setup(self, client: ClientHost, ldap: LDAPHost) -> None:
        self.configure_sssd(client, ldap)

        # Configure ldap client
        client.fs.write(
            "/etc/ldap.conf",
            f"""
            uri ldap://{ldap.hostname}
            sudoers_base ou=sudoers,{ldap.naming_context}
            tls_checkpeer no
            """,
        )

        # Set sudo to use LDAP as source
        self.set_nsswitch(client, {"sudoers": "ldap"})

        # Backup all hosts so we can restore to this state after each test
        super().topology_setup()


class SSSDTopologyController(BaseTopologyController):
    @BackupTopologyController.restore_vanilla_on_error
    def topology_setup(self, client: ClientHost, ldap: LDAPHost) -> None:
        # Configure SSSD to use LDAP as a backend
        self.configure_sssd(client, ldap)

        # Set sudo to use SSSD as source
        self.set_nsswitch(client, {"sudoers": "sss"})

        # Backup all hosts so we can restore to this state after each test
        super().topology_setup()
