"""Client multihost role."""

from __future__ import annotations

import textwrap

from pytest_mh import MultihostRole
from pytest_mh.conn import ProcessError, ProcessResult
from pytest_mh.utils.fs import LinuxFileSystem

from ..hosts.client import ClientHost


class Client(MultihostRole[ClientHost]):
    """
    Kerberos client role.

    Provides unified Python API for managing and testing Kerberos client.

    .. note::

        The role object is instantiated automatically as a dynamic pytest
        fixture by the multihost plugin. You should not create the object
        manually.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.realm: str = self.host.realm
        """
        Kerberos realm.
        """

        self.fs: LinuxFileSystem = LinuxFileSystem(self.host)
        """
        File system manipulation.
        """

    def setup(self) -> None:
        """
        Called before execution of each test.

        Setup client host:

        #. Create krb5.conf

        .. note::

            Original krb5.conf is automatically restored when the test is finished.
        """
        super().setup()
        config = textwrap.dedent(
            f"""
            [logging]
            default = FILE:/var/log/krb5libs.log
            kdc = FILE:/var/log/krb5kdc.log
            admin_server = FILE:/var/log/kadmind.log

            [libdefaults]
            default_realm = {self.host.realm}
            default_ccache_name = KCM:
            dns_lookup_realm = false
            dns_lookup_kdc = false
            ticket_lifetime = 24h
            renew_lifetime = 7d
            forwardable = yes

            [realms]
            {self.host.realm} = {{
              kdc = {self.host.kdc}:88
              admin_server = {self.host.kdc}:749
              max_life = 7d
              max_renewable_life = 14d
            }}

            [domain_realm]
            .{self.host.krbdomain} = {self.host.realm}
            {self.host.krbdomain} = {self.host.realm}
        """
        ).lstrip()
        self.fs.write("/etc/krb5.conf", config, user="root", group="root", mode="0644")

    def kinit(
        self, principal: str, *, password: str, realm: str | None = None, args: list[str] | None = None
    ) -> ProcessResult:
        """
        Run ``kinit`` command.

        Principal can be without the realm part. The realm can be given in
        separate parameter ``realm``, in such case the principal name is
        constructed as ``$principal@$realm``. If the principal does not contain
        realm specification and ``realm`` parameter is not set then the default
        realm is used.

        :param principal: Kerberos principal.
        :type principal: str
        :param password: Principal's password.
        :type password: str
        :param realm: Kerberos realm that is appended to the principal (``$principal@$realm``), defaults to None
        :type realm: str | None, optional
        :param args: Additional parameters to ``klist``, defaults to None
        :type args: list[str] | None, optional
        :return: Command result.
        :rtype: ProcessResult
        """
        if args is None:
            args = []

        if realm is not None:
            principal = f"{principal}@{realm}"

        return self.host.conn.exec(["kinit", *args, principal], input=password)

    def kvno(self, principal: str, *, realm: str | None = None, args: list[str] | None = None) -> ProcessResult:
        """
        Run ``kvno`` command.

        Principal can be without the realm part. The realm can be given in
        separate parameter ``realm``, in such case the principal name is
        constructed as ``$principal@$realm``. If the principal does not contain
        realm specification and ``realm`` parameter is not set then the default
        realm is used.

        :param principal: Kerberos principal.
        :type principal: str
        :param realm: Kerberos realm that is appended to the principal (``$principal@$realm``), defaults to None
        :type realm: str | None, optional
        :param args: Additional parameters to ``klist``, defaults to None
        :type args: list[str] | None, optional
        :return: Command result.
        :rtype: ProcessResult
        """
        if args is None:
            args = []

        if realm is not None:
            principal = f"{principal}@{realm}"

        return self.host.conn.exec(["kvno", *args, principal])

    def klist(self, *, args: list[str] | None = None) -> ProcessResult:
        """
        Run ``klist`` command.

        :param args: Additional parameters to ``klist``, defaults to None
        :type args: list[str] | None, optional
        :return: Command result.
        :rtype: ProcessResult
        """
        if args is None:
            args = []

        return self.host.conn.exec(["klist", *args])

    def kswitch(self, principal: str, realm: str) -> ProcessResult:
        """
        Run ``kswitch -p principal@realm`` command.

        :param principal: Kerberos principal.
        :type principal: str
        :param realm: Kerberos realm that is appended to the principal (``$principal@$realm``)
        :type realm: str
        :return: Command result.
        :rtype: ProcessResult
        """
        if "@" not in principal:
            principal = f"{principal}@{realm}"

        return self.host.conn.exec(["kswitch", "-p", principal])

    def kdestroy(
        self, *, all: bool = False, ccache: str | None = None, principal: str | None = None, realm: str | None = None
    ) -> ProcessResult:
        """
        Run ``kdestroy`` command.

        Principal can be without the realm part. The realm can be given in
        separate parameter ``realm``, in such case the principal name is
        constructed as ``$principal@$realm``. If the principal does not contain
        realm specification and ``realm`` parameter is not set then the default
        realm is used.

        :param all: Destroy all ccaches (``kdestroy -A``), defaults to False
        :type all: bool, optional
        :param ccache: Destroy specific ccache (``kdestroy -c $cache``), defaults to None
        :type ccache: str | None, optional
        :param principal: Destroy ccache for given principal (``kdestroy -p $princ``), defaults to None
        :type principal: str | None, optional
        :param realm: Kerberos realm that is appended to the principal (``$principal@$realm``), defaults to None
        :type realm: str | None, optional
        :return: Command result.
        :rtype: ProcessResult
        """
        args = []

        if all:
            args.append("-A")

        if ccache is not None:
            args.append("-c")
            args.append(ccache)

        if realm is not None and principal is not None:
            principal = f"{principal}@{realm}"

        if principal is not None:
            args.append("-p")
            args.append(principal)

        return self.host.conn.exec(["kdestroy", *args])

    def has_tgt(self, realm: str) -> bool:
        """
        Check that the user has obtained Kerberos Ticket Granting Ticket.

        :param realm: Expected realm for which the TGT was obtained.
        :type realm: str
        :return: True if TGT is available, False otherwise.
        :rtype: bool
        """
        try:
            result = self.klist()
        except ProcessError:
            return False

        return f"krbtgt/{realm}@{realm}" in result.stdout
