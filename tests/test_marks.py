from __future__ import annotations

from collections.abc import Sequence

import pytest
from pytest_mock import MockerFixture

from pytest_mh import (
    KnownTopologyBase,
    KnownTopologyGroupBase,
    MultihostFixture,
    MultihostRole,
    Topology,
    TopologyController,
    TopologyDomain,
    TopologyMark,
)


def test_marks__TopologyMark_init(mocker: MockerFixture):
    topology = Topology(TopologyDomain("test", server=1, client=1))
    fixtures = dict(server="test.server[0]", client="test.client[0]", other="test.client[0]")
    mark = TopologyMark("test-mark", topology, fixtures=fixtures)

    assert mark.name == "test-mark"
    assert mark.topology is topology
    assert mark.fixtures == fixtures
    assert isinstance(mark.controller, TopologyController)

    assert mark.args == {"server", "client", "other"}


def test_marks__TopologyMark_apply(mocker: MockerFixture):
    topology = Topology(TopologyDomain("test", server=1, client=1))
    fixtures = dict(server="test.server[0]", client="test.client[0]", other="test.client[0]", servers="test.servers")
    mark = TopologyMark("test-mark", topology, fixtures=fixtures)

    mock_server = mocker.MagicMock(spec=MultihostRole)
    mock_client = mocker.MagicMock(spec=MultihostRole)
    mock_mh = mocker.MagicMock(spec=MultihostFixture)

    def mock_lookup(path: str):
        match path:
            case "test.servers":
                return [mock_server]
            case "test.server[0]":
                return mock_server
            case "test.client[0]":
                return mock_client
            case _:
                raise ValueError("Unexpected path")

    mock_mh._lookup.side_effect = mock_lookup
    funcargs = {"servers": None, "server": None, "client": None, "other": None}
    expected = {"servers": [mock_server], "server": mock_server, "client": mock_client, "other": mock_client}

    mark.apply(mock_mh, funcargs)
    assert funcargs == expected


def test_marks__TopologyMark_map_fixtures_to_roles(mocker: MockerFixture):
    topology = Topology(TopologyDomain("test", server=1, client=1))
    fixtures = dict(server="test.server[0]", client="test.client[0]", other="test.client[0]", servers="test.servers")
    mark = TopologyMark("test-mark", topology, fixtures=fixtures)

    mock_server = mocker.MagicMock(spec=MultihostRole)
    mock_client = mocker.MagicMock(spec=MultihostRole)
    mock_mh = mocker.MagicMock(spec=MultihostFixture)

    def mock_lookup(path: str):
        match path:
            case "test.servers":
                return [mock_server]
            case "test.server[0]":
                return mock_server
            case "test.client[0]":
                return mock_client
            case _:
                raise ValueError("Unexpected path")

    mock_mh._lookup.side_effect = mock_lookup
    expected = {"servers": [mock_server], "server": mock_server, "client": mock_client, "other": mock_client}

    funcargs = mark.map_fixtures_to_roles(mock_mh)
    assert funcargs == expected


def test_marks__TopologyMark_export():
    topology = Topology(TopologyDomain("test", server=1, client=1))
    fixtures = dict(server="test.server[0]", client="test.client[0]", other="test.client[0]")
    mark = TopologyMark("test-mark", topology, fixtures=fixtures)

    expected = {
        "name": "test-mark",
        "fixtures": fixtures,
        "topology": topology.export(),
    }

    assert mark.export() == expected


class MockKnownTopology(KnownTopologyBase):
    A = TopologyMark("markA", Topology())
    B = TopologyMark("markB", Topology())
    C = TopologyMark("markC", Topology())


class MockKnownTopologyGroup(KnownTopologyGroupBase):
    AB = [MockKnownTopology.A, MockKnownTopology.B]
    BC = [TopologyMark("markB", Topology()), TopologyMark("markC", Topology())]


@pytest.mark.parametrize(
    "marks, expected",
    [
        pytest.param(
            [pytest.mark.topology("simple")],
            [pytest.mark.topology("simple")],
            id="ad-hoc-topology",
        ),
        pytest.param(
            [pytest.mark.topology(TopologyMark("mark", Topology()))],
            [pytest.mark.topology(TopologyMark("mark", Topology()))],
            id="single-topology-mark",
        ),
        pytest.param(
            [
                pytest.mark.topology(TopologyMark("mark1", Topology())),
                pytest.mark.topology(TopologyMark("mark2", Topology())),
            ],
            [
                pytest.mark.topology(TopologyMark("mark1", Topology())),
                pytest.mark.topology(TopologyMark("mark2", Topology())),
            ],
            id="many-topology-marks",
        ),
        pytest.param(
            [pytest.mark.topology([TopologyMark("mark1", Topology()), TopologyMark("mark2", Topology())])],
            [
                pytest.mark.topology(TopologyMark("mark1", Topology())),
                pytest.mark.topology(TopologyMark("mark2", Topology())),
            ],
            id="list-topology-mark",
        ),
        pytest.param(
            [pytest.mark.topology(MockKnownTopology.A)],
            [pytest.mark.topology(MockKnownTopology.A)],
            id="single-known-topology",
        ),
        pytest.param(
            [pytest.mark.topology(MockKnownTopology.A), pytest.mark.topology(MockKnownTopology.B)],
            [pytest.mark.topology(MockKnownTopology.A), pytest.mark.topology(MockKnownTopology.B)],
            id="many-known-topology",
        ),
        pytest.param(
            [pytest.mark.topology([MockKnownTopology.A, MockKnownTopology.B])],
            [pytest.mark.topology(MockKnownTopology.A), pytest.mark.topology(MockKnownTopology.B)],
            id="list-known-topology",
        ),
        pytest.param(
            [pytest.mark.topology(MockKnownTopologyGroup.AB)],
            [pytest.mark.topology(MockKnownTopology.A), pytest.mark.topology(MockKnownTopology.B)],
            id="known-topology-group",
        ),
        pytest.param(
            [pytest.mark.topology(MockKnownTopologyGroup.BC)],
            [
                pytest.mark.topology(TopologyMark("markB", Topology())),
                pytest.mark.topology(TopologyMark("markC", Topology())),
            ],
            id="known-topology-group-mark",
        ),
    ],
)
def test_marks__TopologyMark_ExpandMarkers(mocker: MockerFixture, marks, expected):
    mock_item = mocker.MagicMock(spec=pytest.Item)
    mock_item.iter_markers.return_value = marks

    def assert_equal(left, right):
        assert isinstance(left, Sequence)
        assert isinstance(right, Sequence)
        assert len(left) == len(right), "Different length"

        for left_item, right_item in zip(left, right):
            assert isinstance(left_item, pytest.MarkDecorator)
            assert isinstance(right_item, pytest.MarkDecorator)

            assert len(left_item.args) == 1
            assert len(right_item.args) == 1

            left_item = left_item.args[0]
            right_item = right_item.args[0]

            assert type(left_item) is type(right_item)
            if isinstance(left_item, TopologyMark):
                assert left_item.name == right_item.name
            elif isinstance(left_item, (str, KnownTopologyBase)):
                assert left_item == right_item
            else:
                assert False, "Unknown type"

    expanded = TopologyMark.ExpandMarkers(mock_item)
    assert_equal(expanded, expected)


def test_marks__TopologyMark_Create__invalid_args(mocker: MockerFixture):
    mock_item = mocker.MagicMock(spec=pytest.Function, originalname="test_name")
    mock_item.parent.nodeid = "nodeid"

    decorator = pytest.mark.topology()
    with pytest.raises(ValueError):
        assert TopologyMark.Create(mock_item, decorator.mark)


def test_marks__TopologyMark_Create__topology_mark(mocker: MockerFixture):
    mock_item = mocker.MagicMock(spec=pytest.Function, originalname="test_name")
    mock_item.parent.nodeid = "nodeid"

    topology_mark = TopologyMark("mark", Topology())
    decorator = pytest.mark.topology(topology_mark)
    assert TopologyMark.Create(mock_item, decorator.mark) == topology_mark


def test_marks__TopologyMark_Create__known_topology(mocker: MockerFixture):
    mock_item = mocker.MagicMock(spec=pytest.Function, originalname="test_name")
    mock_item.parent.nodeid = "nodeid"

    decorator = pytest.mark.topology(MockKnownTopology.A)
    assert TopologyMark.Create(mock_item, decorator.mark) == MockKnownTopology.A.value


def test_marks__TopologyMark_Create__args(mocker: MockerFixture):
    mock_item = mocker.MagicMock(spec=pytest.Function, originalname="test_name")
    mock_item.parent.nodeid = "nodeid"

    topology = Topology()
    controller: TopologyController = TopologyController()
    fixtures = {"test": "test.client[0]"}
    decorator = pytest.mark.topology("name", topology, controller=controller, fixtures=fixtures)
    topology_mark = TopologyMark.Create(mock_item, decorator.mark)

    assert topology_mark.name == "name"
    assert topology_mark.topology == topology
    assert topology_mark.controller is controller
    assert topology_mark.fixtures == fixtures


def test_marks__TopologyMark_CreateFromArgs__invalid(mocker: MockerFixture):
    mock_item = mocker.MagicMock(spec=pytest.Function, originalname="test_name")
    mock_item.parent.nodeid = "nodeid"

    topology = Topology()
    controller: TopologyController = TopologyController()
    fixtures = {"test": "test.client[0]"}

    with pytest.raises(ValueError):
        TopologyMark.CreateFromArgs(mock_item, ("name", topology, controller), dict(fixtures=fixtures))


def test_marks__TopologyMark_CreateFromArgs__valid(mocker: MockerFixture):
    mock_item = mocker.MagicMock(spec=pytest.Function, originalname="test_name")
    mock_item.parent.nodeid = "nodeid"

    topology = Topology()
    controller: TopologyController = TopologyController()
    fixtures = {"test": "test.client[0]"}
    topology_mark = TopologyMark.CreateFromArgs(
        mock_item, ("name", topology), dict(controller=controller, fixtures=fixtures)
    )

    assert topology_mark.name == "name"
    assert topology_mark.topology == topology
    assert topology_mark.controller is controller
    assert topology_mark.fixtures == fixtures
