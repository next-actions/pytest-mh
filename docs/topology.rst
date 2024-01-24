Multihost topology
##################

Topology, in the sense of the ``pytest-mh`` plugin, defines what domains, hosts,
and roles are required to run a test. Each test is associated with a particular
topology. If the requirements defined by the topology are not met by the current
multihost configuration then the test is skipped. The requirements are:

* How many domains are needed
* What domain IDs are needed
* How many hosts with given role are needed inside the domain

.. code-block:: yaml
    :caption: Example topology

    domains:
    - id: test
      hosts:
        client: 1
        ldap: 1

Topologies can be nicely written in YAML. The above example describes the
following requirements:

* One domain of id ``test``
* The ``test`` domain has two hosts
* One host implements the ``client`` role and the other host implements the ``ldap`` role

The meaning of the roles is defined by your own extensions of the ``pytest-mh``
plugin. You define the meaning by extending particular multihost classes. See
:doc:`classes` for more information.

It is expected that all hosts implementing the same role within a single
domain are interchangeable. Domain ``id`` must be unique and it is used to
access the hosts, see :ref:`mh-fixture`.

.. note::

    For the purpose of this article we will assume that ``ldap`` represents an
    LDAP server and ``client`` represents the client that talks to the server.
    The domain id ``test`` is used only as a way to group and access the roles
    and hosts and does not have any further meaning.

Using the topology marker
*************************

The topology marker ``@pytest.mark.topology`` is used to associate a particular
topology with given tests. This marker provides information about the topology
that is required to run the test and defines fixture mapping between a short
pytest fixture name and a specific host and role from the topology (this is
explained later in :ref:`mh-fixture`).

The marker is used as:

.. code-block:: python

    @pytest.mark.topology(name, topology, *, fixtures=dict(...))
    def test_example():
        assert True

Where ``name`` is the human-readable topology name that is visible in ``pytest``
verbose output, you can also use this name to filter tests that you want to run
(with the ``-k`` parameter). The next argument, ``topology``, is instance of
:class:`~pytest_mh.Topology` and then follows keyword arguments as a fixture
mapping - we will cover that later.

.. note::

    The topology marker creates an instance of :class:`~pytest_mh.TopologyMark`.
    You can extend this class to add additional information to the topology.

The example topology above would be written as:

.. code-block:: python

    @pytest.mark.topology('ldap', Topology(TopologyDomain('test', client=1, ldap=1)))
    def test_example():
        assert True

.. warning::

    Creating custom topologies and fixture mapping is not recommended and should
    be used only when it is really needed. See :ref:`known-topologies` to learn
    how to use predefined topologies in order to shorten the code and provide
    naming consistency across all tests.

.. _mh-fixture:

Accessing hosts - Deep dive into multihost fixtures
***************************************************

Besides defining topology required by the test, the topology marker also gives
access to the remote hosts through pytest fixtures that are created based on the
topology and the fixture mapping from the topology marker.

This section will go from the very basic low-level access through
:func:`~pytest_mh.mh` fixture and it will advance step by step to a nice
high-level API through dynamic fixture mapping.

Using the mh fixture - low-level API
====================================

Each test that is marked with the ``topology`` marker automatically gains access
to the :func:`~pytest_mh.mh` fixture. This fixture allows you to directly access
domains (:class:`~pytest_mh.MultihostDomain`) and hosts (as
:class:`~pytest_mh.MultihostRole`) that are available in the domain.

.. note::

    It is expected that tests access only high-level API through the role object
    and let the role object talk to the host. Therefore the role objects are
    directly accessible through the :func:`~pytest_mh.mh` fixture instead of
    hosts objects.

To access the hosts through the :func:`~pytest_mh.mh` fixture use:

* ``mh.ns.<domain-id>.<role>`` to access a list of all hosts that implements given role
* ``mh.ns.<domain-id>.<role>[<index>]`` to access a specific host through index starting from 0

The following snippet shows how to access hosts from our topology:

.. code-block:: python

    @pytest.mark.topology('ldap', Topology(TopologyDomain('test', client=1, ldap=1)))
    def test_example(mh: MultihostFixture):
        assert mh.ns.test.client[0].role == 'client'
        assert mh.ns.test.ldap[0].role == 'ldap'

Since the role objects are instances of your own classes (``LDAP`` and
``Client`` for our example), you can also set the type to get the advantage of
Python type hinting.

.. code-block:: python

    @pytest.mark.topology('ldap', Topology(TopologyDomain('test', client=1, ldap=1)))
    def test_example(mh: MultihostFixture):
        client: Client = mh.ns.test.client[0]
        ldap: LDAP = mh.ns.test.ldap[0]

        assert client.role == 'client'
        assert ldap.role == 'ldap'


    @pytest.mark.topology('ldap', Topology(TopologyDomain('test', client=1, ldap=1)))
    def test_example2(mh: MultihostFixture):
        clients: list[Client] = mh.ns.test.client
        ldaps: list[LDAP] = mh.ns.test.ldap

        for client in clients:
            assert client.role == 'client'

        for ldap in ldaps:
            assert ldap.role == 'ldap'

This fixture also makes sure that various ``setup`` methods are called before
each test starts and ``teardown`` methods are executed when the test is finished
which allows you to automatically revert all changes done by the test on the
hosts. See :ref:`setup-and-teardown` for more information.

.. warning::

    Using the :func:`~pytest_mh.mh` fixture directly is not recommended. Please
    see :ref:`dynamic-fixtures` to learn how to simplify access to the hosts by
    creating a fixture mapping.

.. _dynamic-fixtures:

Using dynamic multihost fixtures - high-level API
=================================================

The topology marker allows us to create a mapping between our own fixture name
and specific path inside the :func:`~pytest_mh.mh` fixture by providing
additional keyword-only arguments to the marker.

The example above can be rewritten as:

.. code-block:: python
    :emphasize-lines: 3

    @pytest.mark.topology(
        'ldap', Topology(TopologyDomain('test', client=1, ldap=1)),
        fixtures=dict(client='test.client[0]', ldap='test.ldap[0]')
    )
    def test_example(client: Client, ldap: LDAP):
        assert client.role == 'client'
        assert ldap.role == 'ldap'

By adding the fixture mapping, we tell the ``pytest-mh`` plugin to dynamically
create ``client`` and ``ldap`` fixtures for the test run and set it to the value
of individual hosts inside the :func:`~pytest_mh.mh` fixture which is still used
under the hood.

It is also possible to create a fixture for a group of hosts if our test would
benefit from it.

.. code-block:: python
    :emphasize-lines: 3

    @pytest.mark.topology(
        'ldap', Topology(TopologyDomain('test', client=1, ldap=1)),
        fixtures=dict(clients='test.client', ldap='test.ldap[0]')
    )
    def test_example(clients: list[Client], ldap: LDAP):
        for client in clients:
            assert client.role == 'client'

        assert ldap.role == 'ldap'

.. note::

    We don't have to provide a mapping for every single host, it is up to us
    which hosts will be used. It is even possible to combine fixture mapping
    and at the same time use :func:`~pytest_mh.mh` fixture as well:

    .. code-block:: python
        :emphasize-lines: 5

        @pytest.mark.topology(
            'ldap', Topology(TopologyDomain('test', client=1, ldap=1)),
            fixtures=dict(clients='test.client')
        )
        def test_example(mh: MultihostFixture, clients: list[Client]):
            pass

    It is also possible to request multiple fixtures for a single host. This can
    be used in test parametrization as we will see later in
    :ref:`topology-parametrization`.

    .. code-block:: python
        :emphasize-lines: 3

        @pytest.mark.topology(
            'ldap', Topology(TopologyDomain('test', client=1, ldap=1)),
            fixtures=dict(client='test.client[0]', ldap='test.ldap[0]', provider='test.ldap[0]')
        )
        def test_example(client: Client, provider: GenericProvider):
            pass

.. _known-topologies:

Using known topologies
**********************

It is highly expected that the topology marker is shared between many tests,
therefore it is not very convenient to create it every time from scratch. It is
possible to define a list of known topologies that can be easily shared between
tests.

To create a list of known topologies, you need to subclass
:class:`~pytest_mh.KnownTopologyBase` or
:class:`~pytest_mh.KnownTopologyGroupBase` (for topology parametrization - see
:ref:`topology-parametrization`) and define your topology marker.

.. code-block:: python

    @final
    @unique
    class KnownTopology(KnownTopologyBase):
        LDAP = TopologyMark(
            name="ldap",
            topology=Topology(TopologyDomain("test", client=1, ldap=1)),
            fixtures=dict(client="test.client[0]", ldap="test.ldap[0]"),
        )

Then you can use the known topology directly in the topology marker.

.. code-block:: python

    @pytest.mark.topology(KnownTopology.LDAP)
    def test_example(client: Client, ldap: LDAP):
        assert client.role == 'client'
        assert ldap.role == 'ldap'

.. _topology-parametrization:

Topology parametrization
************************

It is possible to run single test case against multiple topologies. To associate
the test with multiple topologies you can either use multiple topology markers
or single marker that references a known topology group (see
:class:`~pytest_mh.KnownTopologyGroupBase`). Then the test will run multiple
times, once for each assigned topology.

In our example, lets assume that our application can talk to different LDAP
providers, such as Active Directory or FreeIPA. First, we create the known
topologies so it is simple to share the markers between tests.


.. code-block:: python

    @final
    @unique
    class KnownTopology(KnownTopologyBase):
        LDAP = TopologyMark(
            name='ldap',
            topology=Topology(TopologyDomain("test", client=1, ldap=1)),
            fixtures=dict(client='test.client[0]', ldap='test.ldap[0]', provider='test.ldap[0]'),
        )

        IPA = TopologyMark(
            name='ipa',
            topology=Topology(TopologyDomain("test", client=1, ipa=1)),
            fixtures=dict(client='test.client[0]', ipa='test.ipa[0]', provider='test.ipa[0]'),
        )

        AD = TopologyMark(
            name='ad',
            topology=Topology(TopologyDomain("test", client=1, ad=1)),
            fixtures=dict(client='test.client[0]', ad='test.ad[0]', provider='test.ad[0]'),
        )

    class KnownTopologyGroup(KnownTopologyGroupBase):
        AnyProvider = [KnownTopology.AD, KnownTopology.IPA, KnownTopology.LDAP]

Now we can write a parameterized test, the test will be run for all providers.
Notice, how we added the ``provider`` fixture mapping so the host can be
accessed with the provider name (like ``ldap``) or through a generic name
``provider`` that will be used in topology parameterization. The roles need to
implement a common interface so they can be used in tests interchangeably.

.. code-block:: python

    @pytest.mark.topology(KnownTopology.LDAP)
    @pytest.mark.topology(KnownTopology.IPA)
    @pytest.mark.topology(KnownTopology.AD)
    def test_example(client: Client, provider: GenericProvider):
        provider.create_user('test-user')
        assert True

Or the same with the known topology group:

.. code-block:: python

    @pytest.mark.topology(KnownTopologyGroup.AnyProvider)
    def test_example(client: Client, provider: GenericProvider):
        provider.create_user('test-user')
        assert True

If the test is run, you can see that it was run once for each provider:

.. code-block:: console

    $ pytest --mh-config=mhc.yaml -k test_example -v
    ...
    tests/test_basic.py::test_example (ad) PASSED                                                                                                                                                                                   [ 25%]
    tests/test_basic.py::test_example (ipa) PASSED                                                                                                                                                                                  [ 37%]
    tests/test_basic.py::test_example (ldap) PASSED
    ...

.. note::

    It is also possible to combine topology parametrization with
    ``@pytest.mark.parametrize``.

    .. code-block:: python

        @pytest.mark.parametrize('name', ['user-1', 'user 1'])
        @pytest.mark.topology(KnownTopologyGroup.AnyProvider)
        def test_example(client: Client, provider: GenericProvider, name: str):
            provider.create_user(name)
            assert True

    Now the test is executed six times, once for each provider and once per each
    user name value.

    .. code-block:: console

        $ pytest --mh-config=mhc.yaml -k test_example -v
        ...
        tests/test_basic.py::test_example[user-1] (ad) PASSED                                                                                                                                                                                   [ 25%]
        tests/test_basic.py::test_example[user-1] (ipa) PASSED                                                                                                                                                                                  [ 37%]
        tests/test_basic.py::test_example[user-1] (ldap) PASSED                                                                                                                                                                                 [ 50%]
        tests/test_basic.py::test_example[user 1] (ad) PASSED                                                                                                                                                                                   [ 75%]
        tests/test_basic.py::test_example[user 1] (ipa) PASSED                                                                                                                                                                                  [ 87%]
        tests/test_basic.py::test_example[user 1] (ldap) PASSED
        ...
