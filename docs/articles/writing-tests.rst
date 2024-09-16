Writing Tests
#############

Each test that should have access to the remote hosts must be marked with one or
more topology markers. This tells pytest-mh what domains, hosts and roles are
required to run the test. The marker also defines how the
:class:`~pytest_mh.MultihostRole` objects should be accessible from within the
test.

The recommended way is to use :ref:`"dynamic" fixtures
<writing_tests_dynamic_fixtures>`, which are fixtures that do not exist anywhere
in the code but are injected into the test parameters by pytest-mh. It is also
possible to get the access through the :func:`~pytest_mh.mh` fixture, but this
is quite low level and should be avoided, unless you have a valid use case for
it.

.. seealso::

    The topology, topology marker and related information is deeply covered in
    :doc:`extending/multihost-topologies`.

Using the mh fixture - low-level API
====================================

.. warning::

    Using the :func:`~pytest_mh.mh` fixture directly is supported, but not
    recommended. You should avoid it unless you have a valid use case for it.
    However, it is recommended to read this section anyway in order to better
    understand how things work.

The :func:`~pytest_mh.mh` fixture is automatically available to every test and
it returns an instance of :class:`~pytest_mh.MultihostFixture`. This fixture
internally takes care of calling test setup and teardown as well as collecting
test artifacts. It does provide access to all the roles ands hosts, topology and
the topology marker as well as other stuff that are needed for this fixture to
do its job.

There are several attributes that you may find helpful if you need access to
this object.

.. list-table:: mh fixture attributes
    :header-rows: 1

    * - Attribute name
      - Description

    * - :attr:`~pytest_mh.MultihostFixture.ns`
      - Role objects accessible through namespace ``mh.ns.domain_id.role_name``

    * - :attr:`~pytest_mh.MultihostFixture.logger`
      - Multihost logger -- log messages to ``test.log``

    * - :attr:`~pytest_mh.MultihostFixture.roles`
      - List of all role objects

    * - :attr:`~pytest_mh.MultihostFixture.hosts`
      - List of all hosts objects

    * - :attr:`~pytest_mh.MultihostFixture.topology`
      - Current topology assigned to the test

    * - :attr:`~pytest_mh.MultihostFixture.topology_mark`
      - Current topology marker assigned to the test

    * - :attr:`~pytest_mh.MultihostFixture.multihost`
      - Multihost configuration (instance of :class:`~pytest_mh.MultihostConfig`)

.. code-block:: python
    :caption: Example usage of mh fixture

    @pytest.mark.topology('ldap', Topology(TopologyDomain('test', client=1, ldap=1)))
    def test_example(mh: MultihostFixture):
        assert mh.ns.test.client[0].role == 'client'
        assert mh.ns.test.ldap[0].role == 'ldap'

This fixture can be used also in all function-scoped pytest fixtures. The
following example shows how to get direct access to the roles in the test. This,
however, can be achieved by using pytest-mh's :ref:`dynamic fixtures
<writing_tests_dynamic_fixtures>` and their mapping.

.. code-block:: python
    :caption: Example usage of mh fixture inside pytest fixture

    @pytest.fixture
    def client(mh: MultihostFixture) -> Client:
        return mh.ns.test.client[0]

    @pytest.fixture
    def ldap(mh: MultihostFixture) -> LDAP:
        return mh.ns.test.ldap[0]

    @pytest.mark.topology('ldap', Topology(TopologyDomain('test', client=1, ldap=1)))
    def test_example(client: Client, ldap: LDAP):
        assert client.role == 'client'
        assert ldap.role == 'ldap'

.. note::

    Usually, there should not be any reason for you to access the
    :func:`~pytest_mh.mh` fixture directly. The roles are available to the tests
    if a fixture mapping is defined. They are also available in the
    function-scoped fixtures if the fixture is defined with
    :func:`~pytest_mh.mh_fixture` decorator instead of ``@pytest.fixture`` (see:
    :doc:`tips-and-tricks/pytest-fixtures`).

    Most of the other properties are available as standalone fixtures. Go to
    :ref:`writing_tests_builtin_fixtures` to see the list of available fixtures.

.. _writing_tests_dynamic_fixtures:

Using dynamic fixtures - high-level API
=======================================

The topology marker has a ``fixtures`` parameter that defines a mapping between
custom fixture names and specific multihost roles that are required by the
topology. Therefore, instead of accessing the :func:`~pytest_mh.mh` fixture and
defining custom fixtures as a shortcut to the role objects, we can define the
mapping directly in the topology marker:

    .. tab-set::

        .. tab-item:: With dynamic fixtures

            .. code-block:: python
                :emphasize-lines: 3

                @pytest.mark.topology(
                    'ldap', Topology(TopologyDomain('test', client=1, ldap=1)),
                    fixtures=dict(client='test.client[0]', ldap='test.ldap[0]')
                )
                def test_example(client: Client, ldap: LDAP):
                    assert client.role == 'client'
                    assert ldap.role == 'ldap'

        .. tab-item:: Without dynamic fixtures

            .. code-block:: python

                @pytest.fixture
                def client(mh: MultihostFixture) -> Client:
                    return mh.ns.test.client[0]

                @pytest.fixture
                def ldap(mh: MultihostFixture) -> LDAP:
                    return mh.ns.test.ldap[0]

                @pytest.mark.topology('ldap', Topology(TopologyDomain('test', client=1, ldap=1)))
                def test_example(client: Client, ldap: LDAP):
                    assert client.role == 'client'
                    assert ldap.role == 'ldap'

The fixtures are referred to as "dynamic" because they do not exist anywhere as
a standalone pytest fixture function. They are dynamically created by pytest-mh
for each test and the same name refers to a different object in each test. They
can even point to a different host.

    .. code-block:: python
        :emphasize-lines: 5, 18

        @pytest.mark.topology(
            'ldap-a', Topology(TopologyDomain('test', client=1, ldap=1)),
            fixtures=dict(
                client='test.client[0]',
                ldap='test.ldap[0]'
            )
        )
        def test_example_a(client: Client, ldap: LDAP):
            assert client.role == 'client'

            # ldap points to the first host with role ldap found in the test domain
            assert ldap.role == 'ldap'

        @pytest.mark.topology(
            'ldap-b', Topology(TopologyDomain('test', client=1, ldap=1)),
            fixtures=dict(
                client='test.client[0]',
                ldap='test.ldap[1]'
            )
        )
        def test_example_b(client: Client, ldap: LDAP):
            assert client.role == 'client'

            # ldap points to the second host with role ldap found in the test domain
            assert ldap.role == 'ldap'

Fixture path
------------

The fixture path is in the form of ``domain-id.role-name[index]``. The index
refers to a specific host in the order defined by current mhc.yaml and it starts
from zero. The index path can be omitted, in this case it gives you access to
the list of all hosts that implements this role.

.. code-block:: python
    :emphasize-lines: 5, 6

    @pytest.mark.topology(
        'ldap-a', Topology(TopologyDomain('test', client=1, ldap=4)),
        fixtures=dict(
            client='test.client[0]',
            ldap='test.ldap[0]',
            all_ldaps='test.ldap'
        )
    )
    def test_example_a(client: Client, ldap: LDAP, all_ldaps: list[LDAP]):
        assert client.role == 'client'

        assert ldap.role == 'ldap'
        assert ldap in all_ldaps

How to write a test
===================

Previous sections showed how the things around multihost topologies works, so
how should you write a new test? Just follow these steps:

#. Choose the topology or list of topologies that the test will use
#. Define the topology outside the test so it can be reused (the topology is
   most likely already defined in the project)
#. Write a skeleton using the topology
#. Write the test body

.. note::

    It is recommended to use a predefined topology marker so the topology can be
    easily shared between tests. See :doc:`extending/multihost-topologies` for
    more information.

.. code-block:: python
    :caption: Test skeleton

    from framework.topology import KnownTopology

    @pytest.mark.topology(KnownTopology.LDAP)
    def test_skeleton(client: Client, ldap: LDAP):
        pass

The test can also use a :ref:`topology parametrization
<topology_parametrization>`, which can run the test once per each topology. This
is achieved by using a topology group or assigning more then one topology to the
test.


.. tab-set::

    .. tab-item:: Use topology group

        .. code-block:: python
            :caption: Test skeleton

            from framework.topology import KnownTopologyGroup

            @pytest.mark.topology(KnownTopology.AnyProvider)
            def test_skeleton(client: Client, provider: GenericProvider):
                pass

    .. tab-item:: Assign multiple topologies selectively

        .. code-block:: python
            :caption: Test skeleton

            from framework.topology import KnownTopology

            @pytest.mark.topology(KnownTopology.LDAP)
            @pytest.mark.topology(KnownTopology.SSSD)
            @pytest.mark.topology(KnownTopology.Sudoers)
            def test_skeleton(client: Client, provider: GenericProvider):
                pass


.. _writing_tests_builtin_fixtures:

Built-in fixtures
=================

.. list-table:: Built-in fixtures
    :header-rows: 1

    * - Fixture name
      - Return Type
      - Description

    * - :func:`mh <pytest_mh.mh>`
      - :class:`~pytest_mh.MultihostFixture`
      - Low level pytest-mh object.

    * - :func:`mh_config <pytest_mh.mh_config>`
      - :class:`~pytest_mh.MultihostConfig`
      - Main multihost configuration object.

    * - :func:`mh_logger <pytest_mh.mh_logger>`
      - :class:`~pytest_mh.MultihostLogger`
      - Multihost logger, can be used to write messages into the test log.

    * - :func:`mh_topology <pytest_mh.mh_topology>`
      - :class:`~pytest_mh.Topology`
      - Current test's topology object.

    * - :func:`mh_topology_name <pytest_mh.mh_topology_name>`
      - ``str``
      - Current test's topology name.

    * - :func:`mh_topology_mark <pytest_mh.mh_topology_mark>`
      - :class:`~pytest_mh.TopologyMark`
      - Current test's topology marker object.
