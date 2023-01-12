from __future__ import annotations

from pytest_mh import MultihostRole
from pytest_mh.ssh import SSHProcessResult

from ..hosts.kdc import KDCHost


class KDC(MultihostRole[KDCHost]):
    """
    Kerberos KDC role.

    Provides unified Python API for managing objects in the Kerberos KDC.

    .. code-block:: python
        :caption: Creating user and group

        @pytest.mark.topology(KnownTopology.KDC)
        def test_example(kdc: KDC):
            kdc.principal('tuser').add()

    .. note::

        The role object is instantiated automatically as a dynamic pytest
        fixture by the multihost plugin. You should not create the object
        manually.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def kadmin(self, command: str) -> SSHProcessResult:
        """
        Run kadmin command on the KDC.

        :param command: kadmin command
        :type command: str
        """
        result = self.host.ssh.exec(["kadmin.local", "-q", command])

        # Remove "Authenticating as principal root/admin@TEST with password."
        # from the output and keep only output of the command itself.
        result.stdout_lines = result.stdout_lines[1:]
        result.stdout = "\n".join(result.stdout_lines)

        return result

    def list_principals(self) -> list[str]:
        """
        List existing Kerberos principals.

        :return: List of Kerberos principals.
        :rtype: list[str]
        """
        result = self.kadmin("listprincs")
        return result.stdout_lines

    def principal(self, name: str) -> KDCPrincipal:
        """
        Get Kerberos principal object.

        .. code-block:: python
            :caption: Example usage

            @pytest.mark.topology(KnownTopology.KDC)
            def test_example(client: Client, kdc: KDC):
                kdc.principal('tuser').add()

        :param name: Principal name.
        :type name: str
        :return: New principal object.
        :rtype: KDCPrincipal
        """
        return KDCPrincipal(self, name)


class KDCPrincipal(object):
    """
    Kerberos principals management.
    """

    def __init__(self, role: KDC, name: str) -> None:
        """
        :param role: KDC role object.
        :type role: KDC
        :param name: Principal name.
        :type name: str
        """
        self.role: KDC = role
        """KDC role."""

        self.name: str = name
        """Principal name."""

    def add(self, *, password: str | None = "Secret123") -> KDCPrincipal:
        """
        Add a new Kerberos principal.

        Random password is generated if ``password`` is ``None``.

        :param password: Principal's password, defaults to 'Secret123'
        :type password: str | None
        :return: Self.
        :rtype: KDCPrincipal
        """
        if password is not None:
            self.role.kadmin(f'addprinc -pw "{password}" "{self.name}"')
        else:
            self.role.kadmin(f'addprinc -randkey "{self.name}"')

        return self

    def get(self) -> dict[str, str]:
        """
        Retrieve principal information.

        :return: Principal information.
        :rtype: dict[str, str]
        """
        result = self.role.kadmin(f'getprinc "{self.name}"')
        out = {}
        for line in result.stdout_lines:
            (key, value) = line.split(":", maxsplit=1)
            out[key] = value.strip()

        return out

    def delete(self) -> None:
        """
        Delete existing Kerberos principal.
        """
        self.role.kadmin(f'delprinc -force "{self.name}"')

    def set_string(self, key: str, value: str) -> KDCPrincipal:
        """
        Set principal's string attribute.

        :param key: Attribute name.
        :type key: str
        :param value: Atribute value.
        :type value: str
        :return: Self.
        :rtype: KDCPrincipal
        """
        self.role.kadmin(f'setstr "{self.name}" "{key}" "{value}"')
        return self

    def get_strings(self) -> dict[str, str]:
        """
        Get all principal's string attributes.

        :return: String attributes.
        :rtype: dict[str, str]
        """
        result = self.role.kadmin(f'getstrs "{self.name}"')
        out = {}
        for line in result.stdout_lines:
            (key, value) = line.split(":", maxsplit=1)
            out[key] = value.strip()

        return out

    def get_string(self, key: str) -> str | None:
        """
        Set principal's string attribute.

        :param key: Attribute name.
        :type key: str
        :return: Attribute's value or None if not found.
        :rtype: str | None
        """
        attrs = self.get_strings()

        return attrs.get(key, None)
