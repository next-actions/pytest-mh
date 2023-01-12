from __future__ import annotations

from collections import Counter


class TopologyDomain(object):
    """
    Create a new topology domain.

    Topology domain specifies domain type required by the topology as well as
    required roles and number of hosts that must implement these roles. See
    :class:`Topology` for more information.

    The following example defines a topology domain of type ``sssd`` that
    requires two roles: ``client`` and ``ldap`` each provided by one host.

    .. code-block:: python

        TopologyDomain(
            'sssd',
            client=1, ldap=1
        )
    """

    def __init__(self, type: str, **kwargs: int) -> None:
        """
        :param type: Domain type.
        :type type: str
        :param `*kwargs`: Required roles.
        :type `*kwargs`: dict[str, int]
        """

        self.type: str = type
        self.roles: dict[str, int] = kwargs

    def get(self, role: str) -> int:
        """
        Find role and return the number of hosts that must implement this role.

        :param type: Host role to lookup.
        :type type: str
        :raises KeyError: The domain was not found.
        :rtype: int
        """

        return self.roles[role]

    def export(self) -> dict:
        """
        Export the topology domain into a dictionary object that can be easily
        converted to JSON, YAML or other formats.

        .. code-block:: python

            {
                'type': 'sssd',
                'roles': {
                    'client': 1,
                    'ldap': 1
                }
            }

        :rtype: dict
        """

        return {"type": self.type, "hosts": self.roles}

    def satisfies(self, other: "TopologyDomain") -> bool:
        """
        Check if the topology domain satisfies the ``other`` domain.

        Returns ``True`` if the domain types match and this domain contains all
        required roles defined in the ``other`` topology and ``False``
        otherwise.

        :param other: The other topology domain.
        :type other: TopologyDomain
        :rtype: bool
        """

        if self.type != other.type:
            return False

        for role, value in other.roles.items():
            if role not in self or self.get(role) < value:
                return False

        return True

    def __str__(self) -> str:
        return str(self.export())

    def __contains__(self, item: str) -> bool:
        return item in self.roles

    def __eq__(self, other) -> bool:
        return self.export() == other.export()

    def __ne__(self, other) -> bool:
        return self.export() != other.export()


class Topology(object):
    """
    A topology specifies requirements that a multihost configuration must fulfil
    in order to run a test.

    Each topology consist of one or more domains (:class:`TopologyDomain`) that
    defines how many hosts are available inside the domain and what roles are
    implemented.

    The following example defines an ldap topology that consist of one domain of
    type ``sssd`` and requires two roles: ``client`` and ``ldap`` each provided
    by one host.

    .. code-block:: python

        Topology(
            TopologyDomain(
                'sssd',
                 client=1, ldap=1
            )
        )

    This topology can be satisfied for example by the following multihost
    configuration:

    .. code-block:: yaml

        domains:
        - name: ldap.test
          type: sssd
          hosts:
          - name: client
            external_hostname: client.ldap.test
            role: client

          - name: ldap
            external_hostname: master.ldap.test
            role: ldap
    """

    def __init__(self, *domains: TopologyDomain) -> None:
        """
        :param `*args`: Domains that are included in this topology.
        :type `*args`: TopologyDomain
        """

        self.domains = list(domains)

    def get(self, type: str) -> TopologyDomain:
        """
        Find topology domain of the given type and return it.

        :param type: Topology domain type to lookup.
        :type type: str
        :raises KeyError: The domain was not found.
        :rtype: TopologyDomain
        """

        for domain in self.domains:
            if domain.type == type:
                return domain

        raise KeyError(f'Domain "{type}" was not found.')

    def export(self) -> list[dict]:
        """
        Export the topology into a list of dictionaries that can be easily
        converted to JSON, YAML or other formats.

        .. code-block:: python

            [
                {
                    'type': 'sssd',
                    'roles': {
                        'client': 1,
                        'ldap': 1
                }
            ]

        :rtype: dict
        """

        out = []
        for domain in self.domains:
            out.append(domain.export())

        return out

    def satisfies(self, other: "Topology") -> bool:
        """
        Check if the topology satisfies the ``other`` topology.

        Returns ``True`` if this topology contains all domains and required
        roles defined in the ``other`` topology and ``False`` otherwise.

        :param other: The other topology.
        :type other: Topology
        :rtype: bool
        """
        for domain in other.domains:
            if domain.type not in self:
                return False

            if not self.get(domain.type).satisfies(domain):
                return False

        return True

    def __str__(self) -> str:
        return str(self.export())

    def __contains__(self, item: str) -> bool:
        try:
            return self.get(item) is not None
        except KeyError:
            return False

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented

        return self.export() == other.export()

    def __ne__(self, other: object) -> bool:
        return not self == other

    @classmethod
    def FromMultihostConfig(cls, mhc: dict) -> "Topology":
        """
        Create :class:`Topology` from multihost configuration object.

        :param mhc: Multihost configuration object (dictionary)
        :type mhc: dict
        :return: Inferred topology.
        :rtype: Topology
        """

        if mhc is None:
            return cls()

        topology = []
        for domain in mhc.get("domains", []):
            topology.append({"type": domain["type"], "hosts": dict(Counter([x["role"] for x in domain["hosts"]]))})

        domains = [TopologyDomain(x.get("type", "default"), **x["hosts"]) for x in topology]
        return cls(*domains)
