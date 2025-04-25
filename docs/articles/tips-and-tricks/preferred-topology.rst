Preferred Topology
==================

The preferred topology marker ``pytest.mark.preferred_topology`` can be
used if you want the flexibility to run against all topologies, but do not
need to do it all the time. An example could be Nightly builds or a CI where
a single topology is adequate coverage. This will reduce the resources
required to run the tests and their execution times. This is possible by using
the ``pytest.mark.preferred_topology`` marker.

This marks the test with a default topology, deselecting any additional
topologies. ``--mh-ignore-preferred-topology`` can be used to ignore the
marker.

If more than one preferred topology has been defined, only the last topology
will be used. If the preferred topology contains no value, the marker is
ignored.The ``pytest.mark.preferred_topology`` marker accepts three types of
values, :class:`~pytest_mh.TopologyMark` value of
:class:`~pytest_mh.KnownTopologyBase` or ``str``.

.. code-block:: python
    :caption:  Example: set preferred topology to IPA


    @pytest.mark.topology(KnownTopologyGroup.AnyProvider)
    @pytest.mark.preferred_topology(KnownTopology.IPA)
    def test_preferred_mark_known_topology_ipa():
        pass


    @pytest.mark.topology(KnownTopologyGroup.AnyProvider)
    @pytest.mark.preferred_topology("ipa")
    def test_preferred_mark_string_ipa():
        pass
