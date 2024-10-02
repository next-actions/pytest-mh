from __future__ import annotations

import pytest

from pytest_mh import Topology, TopologyDomain


def test_topology__TopologyDomain_init():
    obj = TopologyDomain("test", master=1, client=1)

    assert obj.id == "test"
    assert obj.roles == {"master": 1, "client": 1}


def test_topology__TopologyDomain_get():
    obj = TopologyDomain("test", master=1, client=1)

    assert obj.get("master") == 1
    assert obj.get("client") == 1

    with pytest.raises(KeyError):
        obj.get("unknown")


def test_topology__TopologyDomain_export():
    obj = TopologyDomain("test", master=1, client=1)
    expected = {"id": "test", "hosts": {"master": 1, "client": 1}}

    assert obj.export() == expected


def test_topology__TopologyDomain_satisfies():
    obj1 = TopologyDomain("test", master=1, client=1)
    obj2 = TopologyDomain("test", master=1, client=1)
    obj3 = TopologyDomain("test", master=1, client=2)
    obj4 = TopologyDomain("test", master=1)
    obj5 = TopologyDomain("diff", master=1, client=2)

    assert obj2.satisfies(obj1)
    assert obj3.satisfies(obj1)
    assert not obj4.satisfies(obj1)
    assert not obj5.satisfies(obj1)


def test_topology__TopologyDomain_str():
    obj = TopologyDomain("test", master=1, client=1)

    assert str(obj) == str(obj.export())


def test_topology__TopologyDomain_contains():
    obj = TopologyDomain("test", master=1, client=1)

    assert "master" in obj
    assert "client" in obj
    assert "unknown" not in obj


def test_topology__TopologyDomain_eq():
    obj1 = TopologyDomain("test", master=1, client=1)
    obj2 = TopologyDomain("test", master=1, client=1)
    obj3 = TopologyDomain("test", master=1, client=2)

    assert obj1 == obj2
    assert not obj1 == obj3
    assert not obj2 == obj3


def test_topology__TopologyDomain_ne():
    obj1 = TopologyDomain("test", master=1, client=1)
    obj2 = TopologyDomain("test", master=1, client=1)
    obj3 = TopologyDomain("test", master=1, client=2)

    assert not obj1 != obj2
    assert obj1 != obj3
    assert obj2 != obj3


def test_topology__Topology_init():
    dom1 = TopologyDomain("test", master=1)
    dom2 = TopologyDomain("test2", master=1)
    obj = Topology(dom1, dom2)

    assert obj.domains == [dom1, dom2]


def test_topology__Topology_get():
    dom1 = TopologyDomain("test", master=1)
    dom2 = TopologyDomain("test2", master=1)
    obj = Topology(dom1, dom2)

    assert obj.get("test") == dom1
    assert obj.get("test2") == dom2

    with pytest.raises(KeyError):
        obj.get("unknown")


def test_topology__Topology_export():
    dom1 = TopologyDomain("test", master=1)
    dom2 = TopologyDomain("test2", master=1)
    obj = Topology(dom1, dom2)

    assert obj.export() == [dom1.export(), dom2.export()]


def test_topology__Topology_satisfies():
    dom1_1 = TopologyDomain("test", master=1)
    dom1_2 = TopologyDomain("test2", master=1)
    obj1 = Topology(dom1_1, dom1_2)

    dom2_1 = TopologyDomain("test", master=1)
    dom2_2 = TopologyDomain("test2", master=1)
    obj2 = Topology(dom2_1, dom2_2)

    dom3_1 = TopologyDomain("test", master=1, client=1)
    dom3_2 = TopologyDomain("test2", master=1)
    obj3 = Topology(dom3_1, dom3_2)

    dom4_1 = TopologyDomain("test3", master=1, client=1)
    dom4_2 = TopologyDomain("test2", master=1)
    obj4 = Topology(dom4_1, dom4_2)

    assert obj2.satisfies(obj1)
    assert obj1.satisfies(obj2)
    assert obj3.satisfies(obj1)
    assert obj3.satisfies(obj2)
    assert not obj4.satisfies(obj3)
    assert not obj1.satisfies(obj3)
    assert not obj2.satisfies(obj3)


def test_topology__Topology_str():
    dom1 = TopologyDomain("test", master=1)
    dom2 = TopologyDomain("test2", master=1)
    obj = Topology(dom1, dom2)

    assert str(obj) == str([dom1.export(), dom2.export()])


def test_topology__Topology_contains():
    dom1 = TopologyDomain("test", master=1)
    dom2 = TopologyDomain("test2", master=1)
    obj = Topology(dom1, dom2)

    assert "test" in obj
    assert "test2" in obj
    assert "unknown" not in obj


def test_topology__Topology_eq():
    dom1_1 = TopologyDomain("test", master=1)
    dom1_2 = TopologyDomain("test2", master=1)
    obj1 = Topology(dom1_1, dom1_2)

    dom2_1 = TopologyDomain("test", master=1)
    dom2_2 = TopologyDomain("test2", master=1)
    obj2 = Topology(dom2_1, dom2_2)

    dom3_1 = TopologyDomain("test", master=1, client=1)
    dom3_2 = TopologyDomain("test2", master=1)
    obj3 = Topology(dom3_1, dom3_2)

    assert obj1 == obj2
    assert not obj1 == obj3
    assert not obj2 == obj3


def test_topology__Topology_ne():
    dom1_1 = TopologyDomain("test", master=1)
    dom1_2 = TopologyDomain("test2", master=1)
    obj1 = Topology(dom1_1, dom1_2)

    dom2_1 = TopologyDomain("test", master=1)
    dom2_2 = TopologyDomain("test2", master=1)
    obj2 = Topology(dom2_1, dom2_2)

    dom3_1 = TopologyDomain("test", master=1, client=1)
    dom3_2 = TopologyDomain("test2", master=1)
    obj3 = Topology(dom3_1, dom3_2)

    assert not obj1 != obj2
    assert obj1 != obj3
    assert obj2 != obj3


def test_topology__Topology_FromMultihostConfig():
    mhc = {
        "domains": [
            {
                "id": "test",
                "hosts": [
                    {"name": "ipa", "external_hostname": "ipa.test", "role": "master"},
                    {"name": "client", "external_hostname": "client.test", "role": "client"},
                ],
            },
            {
                "id": "test2",
                "hosts": [
                    {"name": "client", "external_hostname": "client.test", "role": "client"},
                    {"name": "client2", "external_hostname": "client2.test", "role": "client"},
                ],
            },
        ]
    }

    dom1 = TopologyDomain("test", master=1, client=1)
    dom2 = TopologyDomain("test2", client=2)
    obj1 = Topology(dom1, dom2)
    obj2 = Topology.FromMultihostConfig(mhc)

    assert obj1 == obj2
    assert Topology() == Topology.FromMultihostConfig(None)
