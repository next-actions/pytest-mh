from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping, Tuple

import pytest

from .topology import Topology
from .topology_controller import TopologyController

if TYPE_CHECKING:
    from .fixtures import MultihostFixture


class TopologyMark(object):
    """
    Topology mark is used to describe test case requirements. It defines:

    * **name**, that is used to identify topology in pytest output
    * **topology** (:class:Topology) that is required to run the test
    * **controller** (:class:TopologyController) to provide per-topology hooks, optional
    * **fixtures** that are available during the test run, optional

    .. code-block:: python
        :caption: Example usage

        @pytest.mark.topology(
            name, topology,
            controller=controller,
            fixture=dict(fixture1='path1', fixture2='path2', ...)
        )
        def test_fixture_name(fixture1: BaseRole, fixture2: BaseRole, ...):
            assert True

    Fixture path points to a host in the multihost configuration and can be
    either in the form of ``$domain-id.$role`` (all host of given role) or
    ``$domain-id.$role[$index]`` (specific host on given index).

    The ``name`` is visible in verbose pytest output after the test name, for example:

    .. code-block:: console

        tests/test_basic.py::test_case (topology-name) PASSED
    """

    def __init__(
        self,
        name: str,
        topology: Topology,
        *,
        controller: TopologyController | None = None,
        fixtures: dict[str, str] | None = None,
    ) -> None:
        """
        :param name: Topology name used in pytest output.
        :type name: str
        :param topology: Topology required to run the test.
        :type topology: Topology
        :param controller: Topology controller, defaults to None
        :type controller: TopologyController | None, optional
        :param fixtures: Dynamically created fixtures available during the test run, defaults to None
        :type fixtures: dict[str, str] | None, optional
        """
        self.name: str = name
        """Topology name."""

        self.topology: Topology = topology
        """Multihost topology."""

        self.controller: TopologyController = controller if controller is not None else TopologyController()
        """Multihost topology controller."""

        self.fixtures: dict[str, str] = fixtures if fixtures is not None else {}
        """Dynamic fixtures mapping."""

        self.mapping: dict[str, list[str]] = {}

        for fixture, target in self.fixtures.items():
            self.mapping.setdefault(target, list()).append(fixture)

    @property
    def args(self) -> set[str]:
        """
        Names of all dynamically created fixtures.
        """

        return set(self.fixtures.keys())

    def apply(self, mh: MultihostFixture, funcargs: dict[str, Any]) -> None:
        """
        Create required fixtures by modifying pytest.Item.funcargs.

        :param mh: _description_
        :type mh: Multihost
        :param funcargs: Pytest test item ``funcargs`` that will be modified.
        :type funcargs: dict[str, Any]
        """

        for path, names in self.mapping.items():
            value = mh._lookup(path)
            for name in names:
                if name in funcargs:
                    funcargs[name] = value

    def export(self) -> dict:
        """
        Export the topology mark into a dictionary object that can be easily
        converted to JSON, YAML or other formats.

        .. code-block:: python

            {
                'name': 'client',
                'fixtures': { 'client': 'test.client[0]' },
                'topology': [
                    {
                        'id': 'test',
                        'hosts': { 'client': 1 }
                    }
                ]
            }

        :rtype: dict
        """

        return {
            "name": self.name,
            "fixtures": self.fixtures,
            "topology": self.topology.export(),
        }

    @classmethod
    def ExpandMarkers(cls, item: pytest.Item) -> list[pytest.Mark]:
        out = []
        for mark in item.iter_markers("topology"):
            # We need to use generic classes in order to avoid circular import
            if isinstance(mark.args[0], KnownTopologyGroupBase) and isinstance(mark.args[0].value, list):
                for topology in mark.args[0].value:
                    out.append(pytest.mark.topology(topology))
                continue

            out.append(mark)

        return out

    @classmethod
    def Create(cls, item: pytest.Function, mark: pytest.Mark) -> TopologyMark:
        """
        Create instance of :class:`TopologyMark` from ``@pytest.mark.topology``.

        :raises ValueError:
        :rtype: TopologyMark
        """
        nodeid = item.parent.nodeid if item.parent is not None else ""
        error = f"{nodeid}::{item.originalname}: invalid arguments for @pytest.mark.topology"

        if not mark.args or len(mark.args) > 3:
            raise ValueError(error)

        # Constructor for KnownTopologyBase
        if isinstance(mark.args[0], KnownTopologyBase):
            if len(mark.args) != 1:
                raise ValueError(error)

            if not isinstance(mark.args[0].value, cls):
                raise ValueError(error)

            return mark.args[0].value

        # Generic constructor.
        return cls._CreateFromArgs(item, mark.args, mark.kwargs)

    @classmethod
    def _CreateFromArgs(cls, item: pytest.Function, args: Tuple, kwargs: Mapping[str, Any]) -> TopologyMark:
        """
        Create :class:`TopologyMark` from pytest marker arguments.

        .. warning::

            This should only be called internally. You can inherit from
            :class:`TopologyMark` and override this in order to add additional
            attributes to the marker.

        :param item: Pytest item.
        :type item: pytest.Function
        :param args: Pytest mark positional arguments.
        :type args: Any
        :param kwargs: Pytest mark keyword arguments arguments.
        :type kwargs: Mapping[str, Any]
        :raises ValueError: If the marker is invalid.
        :return: Instance of TopologyMark.
        :rtype: TopologyMark
        """
        # First two parameters are positional, the rest are keyword arguments.
        if len(args) != 2:
            nodeid = item.parent.nodeid if item.parent is not None else ""
            error = f"{nodeid}::{item.originalname}: invalid arguments for @pytest.mark.topology"
            raise ValueError(error)

        name = args[0]
        topology = args[1]
        controller = kwargs.get("controller", None)
        fixtures = {k: str(v) for k, v in kwargs.get("fixtures", {}).items()}

        return cls(name, topology, controller=controller, fixtures=fixtures)


class KnownTopologyBase(Enum):
    """
    Base class for a predefined set of topologies.

    Users of this plugin may inherit from this class in order to created a
    predefined, well-known set of topology markers.

    .. code-blocK:: python
        :caption: Example usage

        @final
        @unique
        class KnownTopology(KnownTopologyBase):
            A = TopologyMark(
                name='A',
                topology=Topology(TopologyDomain('test', a=1)),
                fixtures=dict(a='test.a[0]'),
            )

            B = TopologyMark(
                name='B',
                topology=Topology(TopologyDomain('test', b=1)),
                fixtures=dict(b='test.b[0]'),
            )


        @pytest.mark.topology(KnownTopology.A)
        def test_a(a: ARole):
            pass

        @pytest.mark.topology(KnownTopology.B)
        def test_b(b: BRole):
            pass
    """

    pass


class KnownTopologyGroupBase(Enum):
    """
    Base class for a predefined set of list of topologies.

    Users of this plugin may inherit from this class in order to create a
    predefined, well-known set of list of topology markers that can be used
    directly in ``@pytest.mark.topology`` to enable topology parametrization for
    a test case.

    .. code-blocK:: python
        :caption: Example usage

        @final
        @unique
        class KnownTopologyGroup(KnownTopologyGroupBase):
            All = [
                TopologyMark(
                    name='A',
                    topology=Topology(TopologyDomain('test', a=1)),
                    fixtures=dict(a='test.a[0]', generic='test.a[0]'),
                ),

                B = TopologyMark(
                    name='B',
                    topology=Topology(TopologyDomain('test', b=1)),
                    fixtures=dict(b='test.b[0]', generic='test.a[0]'),
                )
            ]


        # Will run once for A, once for B
        @pytest.mark.topology(KnownTopologyGroup.All)
        def test_all(generic: GenericRole):
            pass
    """

    pass
