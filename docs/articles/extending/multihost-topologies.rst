Multihost Topologies
####################

Multihost topology is the core of pytest-mh. It defines the requirements of a
test -- what multihost domains and roles (and how many) are required to run the
test. If the current environment defined in the configuration file does not meet
the requirements of the topology then the test is silently skipped (in pytest
terminology the test is not collected) and you will not even see it in the
results.

Using the topology, we can say that a test requires "1 client and 1 server".
Maybe, you are using external authentication provider with Kerberos, so you
might say that the test requires "1 client, 1 server and 1 KDC". Or you want to
test that data replication and load balancer works correctly: "1 client, 3
servers and 1 load balancer".

The following snippets shows how this can be represented in the configuration
file:

.. tab-set::

    .. tab-item:: 1 client, 1 server

        .. code-block:: yaml

            domains:
            - id: myapp
              hosts:
              - hostname: client.myapp.test
                role: client
              - hostname: server.myapp.test
                role: server

    .. tab-item:: 1 client, 1 server, 1 KDC

        .. code-block:: yaml

            domains:
            - id: myapp
              hosts:
              - hostname: client.myapp.test
                role: client
              - hostname: server.myapp.test
                role: server
            - id: authprovider
              hosts:
              - hostname: kdc.authprovider.test
                role: kdc

    .. tab-item:: 1 client, 3 server, 1 load balancer

        .. code-block:: yaml

            domains:
            - id: myapp
              hosts:
              - hostname: client.myapp.test
                role: client
              - hostname: server1.myapp.test
                role: server
              - hostname: replica1.myapp.test
                role: server
              - hostname: replica2.myapp.test
                role: server
              - hostname: balancer.myapp.test
                role: balancer

.. note::

    See that all three servers from the third example are placed inside a single
    multihost domain. This is because all these servers contains the same data
    and it should not matter to which one the client talks to. If they serve
    different data, they should be placed in different multihost domains.

Topology Marker
===============

Pytest-mh implements a new marker ``@pytest.mark.topology`` which is converted
into an instance of :class:`~pytest_mh.TopologyMark`. This marker is used to
assign a topology to a test. One test can be associated with multiple topologies
-- this is called :ref:`topology parametrization <topology_parametrization>`. In
this case, the test is multiplied and run once for all assigned topologies,
therefore it is possible to re-use the test code for different setups/backends.

The ``@pytest.mark.topology`` can take different types of arguments in order to
instantiate the marker:

* individual arguments, see :ref:`adhoc_topology`
* single instance or list of :class:`~pytest_mh.TopologyMark`, see :ref:`predefined_topology`
* values from :class:`~pytest_mh.KnownTopologyBase` or
  :class:`~pytest_mh.KnownTopologyGroupBase` enums (**recommended**), see
  :ref:`known_topology`

.. _adhoc_topology:

Ad-hoc Topologies
-----------------

If you plan to use the topology only once, you can define it directly on the
test inside ``@pytest.mark.topology``. The arguments are the same as the
arguments of the :class:`~pytest_mh.TopologyMark` constructor.

.. code-block:: python
    :caption: Example ad-hoc topology

    @pytest.mark.topology(
        "client-server",
        Topology(TopologyDomain("myproject", client=1, server=1)),
        controller=TopologyController(),
        fixtures=dict(client='myproject.client[0]', server='myproject.server[0]')
    )
    def test_example(client: ClientRole, server: ServerRole):
        assert True

In this example, the first argument ``client-server`` is the topology name that
will be visible in the logs and pytest output. The second argument is the
definition of the topology, see :class:`~pytest_mh.Topology` and
:class:`~pytest_mh.TopologyDomain`. These are the only positional arguments,
everything else must be set as a keyword argument.

The built-in :class:`~pytest_mh.TopologyMark` supports ``controller`` (defaults
to an instance of :class:`~pytest_mh.TopologyController`) and ``fixtures`` which
defines mapping between hosts and pytest fixtures available to the test.

The ``fixtures`` argument is a dictionary, where key is the fixture name and
value is the path to the hosts in the form: ``$domain-id.$role[$index]``. This
will point to a role object of a specific host from the configuration file. It
is also possible to reference a group of hosts by omitting the index:
``$domain-id.$role``. Each path can be set multiple times, which can be useful
for :ref:`topology_parametrization`.

.. code-block:: python
    :caption: Example ad-hoc topology that references a group of hosts

    @pytest.mark.topology(
        "client-two-servers",
        Topology(TopologyDomain("myproject", client=1, server=2)),
        controller=TopologyController(),
        fixtures=dict(client='myproject.client[0]', servers='myproject.server')
    )
    def test_example(client: ClientRole, servers: list[ServerRole]):
        assert True

.. note::

    Using ad-hoc topologies is not generally recommended. You should always
    prefer to use :ref:`predefined_topology` or :ref:`known_topology`, since it
    makes the code more readable and the topology can be easily reused once you
    need it.

.. _predefined_topology:

Pre-defined Topologies
----------------------

Pre-defined topologies can be safely reused by other tests. You can create a
pre-defined topology by instantiating a :class:`~pytest_mh.TopologyMark` class
and assigning it to a variable.

.. code-block:: python
    :caption: Example pre-defined topology

    CLIENT_SERVER = TopologyMark(
        "client-server",
        Topology(TopologyDomain("myproject", client=1, server=1)),
        controller=TopologyController(),
        fixtures=dict(client='myproject.client[0]', server='myproject.server[0]')
    )
    """Topology: 1 client, 1 server"""


    @pytest.mark.topology(CLIENT_SERVER)
    def test_example_1(client: ClientRole, server: ServerRole):
        assert True


    @pytest.mark.topology(CLIENT_SERVER)
    def test_example_2(client: ClientRole, server: ServerRole):
        assert True

.. seealso::

    See :ref:`adhoc_topology` for description of
    :class:`~pytest_mh.TopologyMark` arguments.

.. _known_topology:

KnownTopology and KnownTopologyGroup
------------------------------------

This is kind of pre-defined topology, that groups multiple topologies in a
single :class:`~enum.Enum` class. This makes it a little bit easier to use than
ungrouped :ref:`pre-defined topologies <predefined_topology>`, since you only
have to import one object to your test module and you get access to all
topologies -- you do not have to import each topology separately.

This is done by extending :class:`~pytest_mh.KnownTopologyBase` to define your
project's topologies and :class:`~pytest_mh.KnownTopologyGroupBase` to define
list of topologies for :ref:`topology parametrization
<topology_parametrization>`.

.. code-blocK:: python
    :caption: Example of KnownTopology

    @final
    @unique
    class KnownTopology(KnownTopologyBase):
        CLIENT_SERVER = TopologyMark(
            "client-server",
            Topology(TopologyDomain("myproject", client=1, server=1)),
            controller=TopologyController(),
            fixtures=dict(client='myproject.client[0]', server='myproject.server[0]', servers='myproject.server')
        )

        CLIENT_TWO_SERVERS = TopologyMark(
            "client-two-servers",
            Topology(TopologyDomain("myproject", client=1, server=2)),
            controller=TopologyController(),
            fixtures=dict(client='myproject.client[0]', servers='myproject.server')
        )


    @pytest.mark.topology(KnownTopology.CLIENT_SERVER)
    def test_example_1(client: ClientRole, server: ServerRole):
        pass

    @pytest.mark.topology(KnownTopology.CLIENT_TWO_SERVERS)
    def test_example_2(client: ClientRole, servers: list[ServerRole]):
        pass

.. code-blocK:: python
    :caption: Example of KnownTopologyGroup

    @final
    @unique
        class KnownTopologyGroup(KnownTopologyGroupBase):
            All = [
                KnownTopology.CLIENT_SERVER,
                KnownTopology.CLIENT_TWO_SERVERS,
            ]


    # this test will run for both CLIENT_SERVER and CLIENT_TWO_SERVERS
    @pytest.mark.topology(KnownTopologyGroup.All)
    def test_example(client: ClientRole, servers: list[ServerRole]):
        pass

.. note::

    Notice, that in order to allow topology parametrization, we added
    ``servers='myproject.server'`` to ``CLIENT_SERVER`` topology as well. This
    is explained in more detail in :ref:`topology_parametrization`.

Extending Topology Marker
-------------------------

The topology marker can be extended to provide more parameters or additional
functionality. In order to do this, subclass
:class:`~pytest_mh.TopologyMark` and override
:meth:`~pytest_mh.TopologyMark.CreateFromArgs` and
:meth:`~pytest_mh.TopologyMark.export`.

.. code-block:: python
    :caption: Example of custom topology marker that adds new parameter
    :emphasize-lines: 13,17,22,38
    :linenos:

    class MyProjectTopologyMark(TopologyMark):
        """
        Add ``new_param`` parameter to the built-in topology marker.
        """

        def __init__(
            self,
            name: str,
            topology: Topology,
            *,
            controller: TopologyController | None = None,
            fixtures: dict[str, str] | None = None,
            new_param: str | None = None,
        ) -> None:
            super().__init__(name, topology, controller=controller, fixtures=fixtures)

            self.new_param: str | None = new_param
            """New parameter for my project."""

        def export(self) -> dict:
            d = super().export()
            d["new_param"] = self.new_param

            return d

        @classmethod
        def CreateFromArgs(cls, item: pytest.Function, args: Tuple, kwargs: Mapping[str, Any]) -> Self:
            # First three parameters are positional, the rest are keyword arguments.
            if len(args) != 2 and len(args) != 3:
                nodeid = item.parent.nodeid if item.parent is not None else ""
                error = f"{nodeid}::{item.originalname}: invalid arguments for @pytest.mark.topology"
                raise ValueError(error)

            name = args[0]
            topology = args[1]
            controller = kwargs.get("controller", None)
            fixtures = {k: str(v) for k, v in kwargs.get("fixtures", {}).items()}
            new_param = kwargs.get("new_param", None)

            return cls(name, topology, controller=controller, fixtures=fixtures, new_param=new_param)

Then make this a topology marker type by setting
:attr:`~pytest_mh.MultihostConfig.TopologyMarkClass` in your
:class:`~pytest_mh.MultihostConfig` class.

.. code-block:: python
    :emphasize-lines: 3,5
    :linenos:

    class MyProjectConfig(MultihostConfig):
        @property
        def TopologyMarkClass(self) -> Type[TopologyMark]:
            # Set a custom topology marker type
            return MyProjectTopologyMark

Topology Controller
===================

Pytest-mh allows you to run tests against multiple topologies in one pytest run.
It is not always possible or desired to provide distinct set of host for each
topology, instead the hosts are usually being reused. However, each topology
typically requires different environment setup.
:class:`~pytest_mh.TopologyController` gives you access to topology setup and
teardown as well as the possibility to skip all tests for given topology if the
environment is not fully setup to run it.

With the topology controller, you can:

* setup hosts before any test for this topology is run (see: :meth:`~pytest_mh.TopologyController.topology_setup`)
* teardown hosts after all tests for this topology are finished (see: :meth:`~pytest_mh.TopologyController.topology_teardown`)
* setup hosts before each test that utilizes this topology (see: :meth:`~pytest_mh.TopologyController.setup`)
* teardown hosts after each test that utilizes this topology (see: :meth:`~pytest_mh.TopologyController.teardown`)
* skip all test for this topology if certain condition is not met (see: :meth:`~pytest_mh.TopologyController.skip`)
* set topology specific artifacts (see: :meth:`~pytest_mh.TopologyController.set_artifacts`)

.. code-block:: python
    :caption: Example topology controller

    class LDAPClientFeatureController(TopologyController[MyProjectConfig]):
        """
        - skip all tests for this topology if the client does not support LDAP connections
        - configure the client to use LDAP connections on topology setup
        - revert configuration on topology teardown
        - fetch logs from the configuration change
        """

        def set_artifacts(self, client: ClientHost) -> None:
            self.artifacts.topology_setup[client] = {"/var/log/enable_ldap.log"}
            self.artifacts.topology_teardown[client] = {"/var/log/disable_ldap.log"}

        def skip(self, client: ClientHost) -> str | None:
            result = client.conn.run('is ldap feature enabled', raise_on_error=False)
            if result.rc != 0:
                return "LDAP feature is not supported on client"

            return None

        def topology_setup(self, client: ClientHost):
            client.conn.run('enable LDAP on client > /var/log/enable_ldap.log')

        def topology_teardown(self, client: ClientHost):
            client.conn.run('disable LDAP on client > /var/log/disable_ldap.log')

.. seealso::

    * Documentation for :class:`~pytest_mh.TopologyController`
    * :doc:`../life-cycle/artifacts-collection`
    * :doc:`../life-cycle/setup-and-teardown`

.. warning::

    When extending the :class:`~pytest_mh.TopologyController`, keep in mind that
    it is instantiated early in the plugin life but actually initialized much
    later. Therefore most attributes can not be accessed from the constructor.

    For this reason, it is recommended to only declare properties in the
    constructor but place your initialization call in
    :meth:`~pytest_mh.TopologyController.init`. Do not forget to call
    ``super().init(*args, **kwargs)`` as the first step.

    .. code-block:: python

        class MyProjectTopologyController(TopologyController[MyProjectMultihostConfig]):
            def __init__(self) -> None:
                super().__init__()

                self.my_project_param: bool = False

            def _init(self, *args, **kwargs):
                super().init(*args, **kwargs)
                self.my_project_param = self.multihost.my_project_param

.. seealso::

    The topology controller can also be used to implement automatic setup,
    backup and restore of the topology environment. See
    :doc:`../tips-and-tricks/backup-restore` for tips on how to achieve that
    with :class:`~pytest_mh.BackupTopologyController`.

.. _topology_parametrization:

Topology Parametrization
========================

A test parametrization is a way to share a test code for different input
arguments and therefore test different configurations or user inputs easily and
thus quickly extend the code coverage. Pytest allows this by using the
``@pytest.mark.parametrize`` `mark <pytest-parametrize_>`_.

Similar functionality can be achieved with topologies when the same test code is
run against multiple topologies. This is useful for many situations, as it is
often desirable to test the same functionality with different configurations
which, however, also require a different environment setup (different multihost
topology). For example:

* A client application is able to connect to multiple different backends. This
  is the case of SSSD, that implements a system interface for retrieving user
  information but is able to fetch the data from various LDAP-like sources:
  LDAP, Active Directory, FreeIPA and SambaDC.

* Another example would be an application that uses some SQL database but allows
  to use different servers such as MariaDB or PostreSQL.

* Or for instance, there is a DNS client library that supports plain-text DNS
  queries but also encryption over TLS, HTTPS and QUIC. It is possible to have
  one test for hostname resolution but let the client library use all transfer
  protocols, one by one.

In each case, it is desirable to have a single test which, however, is run with
different backends or server configurations. To provide a real world example,
we can check out one of the basic SSSD tests. This test has multiple topologies
assigned and it is run once per each topology: LDAP, IPA, Samba and AD.

.. tab-set::

    .. tab-item:: With topology parametrization

        .. code-block:: python
            :caption: Only single test is required with topology parametrization

            @pytest.mark.topology(KnownTopologyGroup.AnyProvider)
            def test_id__supplementary_groups(client: Client, provider: GenericProvider):
                u = provider.user("tuser").add()
                provider.group("tgroup_1").add().add_member(u)
                provider.group("tgroup_2").add().add_member(u)

                client.sssd.start()
                result = client.tools.id("tuser")

                assert result is not None
                assert result.user.name == "tuser"
                assert result.memberof(["tgroup_1", "tgroup_2"])

    .. tab-item:: Without topology parametrization

        .. code-block:: python
            :caption: Four tests are required without topology parametrization

            @pytest.mark.topology(KnownTopology.LDAP)
            def test_id_ldap__supplementary_groups(client: Client, ldap: LDAP):
                u = ldap.user("tuser").add()
                ldap.group("tgroup_1").add().add_member(u)
                ldap.group("tgroup_2").add().add_member(u)

                client.sssd.start()
                result = client.tools.id("tuser")

                assert result is not None
                assert result.user.name == "tuser"
                assert result.memberof(["tgroup_1", "tgroup_2"])


              @pytest.mark.topology(KnownTopology.IPA)
              def test_id_ipa__supplementary_groups(client: Client, ipa: IPA):
                  u = ipa.user("tuser").add()
                  ipa.group("tgroup_1").add().add_member(u)
                  ipa.group("tgroup_2").add().add_member(u)

                  client.sssd.start()
                  result = client.tools.id("tuser")

                  assert result is not None
                  assert result.user.name == "tuser"
                  assert result.memberof(["tgroup_1", "tgroup_2"])


              @pytest.mark.topology(KnownTopology.AD)
              def test_id_ad__supplementary_groups(client: Client, ad: AD):
                  u = ad.user("tuser").add()
                  ad.group("tgroup_1").add().add_member(u)
                  ad.group("tgroup_2").add().add_member(u)

                  client.sssd.start()
                  result = client.tools.id("tuser")

                  assert result is not None
                  assert result.user.name == "tuser"
                  assert result.memberof(["tgroup_1", "tgroup_2"])


              @pytest.mark.topology(KnownTopology.Samba)
              def test_id_samba__supplementary_groups(client: Client, samba: Samba):
                  u = samba.user("tuser").add()
                  samba.group("tgroup_1").add().add_member(u)
                  samba.group("tgroup_2").add().add_member(u)

                  client.sssd.start()
                  result = client.tools.id("tuser")

                  assert result is not None
                  assert result.user.name == "tuser"
                  assert result.memberof(["tgroup_1", "tgroup_2"])

.. seealso::

    See the `sssd-test-framework sources <sssd_framework_topology_>`_ to see how
    the ``AnyProvider`` topology group is defined.

The ``KnownTopologyGroup.AnyProvider`` is a list of LDAP, IPA, Samba and AD
topologies, therefore the test is run for each topology from this list, four
times in total. The topology group makes it easy to parametrize tests when this
group is used quite often. However, it is also possible to use the topology
marker multiple times, therefore we can achieve the same with:

.. code-block:: python

    @pytest.mark.topology(KnownTopology.AD)
    @pytest.mark.topology(KnownTopology.LDAP)
    @pytest.mark.topology(KnownTopology.IPA)
    @pytest.mark.topology(KnownTopology.Samba)
    def test_id__supplementary_groups(client: Client, provider: GenericProvider):

Notice, that individual tests when not using topology parametrization are
accessing the backend role via specific types: ``LDAP``, ``IPA``, ``AD`` and
``Samba`` as well as specific fixture names ``ldap``, ``ipa``, ``ad`` and
``samba``. This is not possible with topology parametrization since it is
required to use a generic interface that will work for all topologies used by
the test. Therefore the SSSD's topologies defines the ``provider`` fixture and a
generic type ``GenericProvider`` that is implemented by the individual backends.

.. code-block:: python
    :caption: Snippet from sssd-test-framework showing the topologies
    :emphasize-lines: 7, 17, 27, 37
    :linenos:

    LDAP = SSSDTopologyMark(
        name="ldap",
        topology=Topology(TopologyDomain("sssd", client=1, ldap=1, nfs=1, kdc=1)),
        controller=LDAPTopologyController(),
        domains=dict(test="sssd.ldap[0]"),
        fixtures=dict(
            client="sssd.client[0]", ldap="sssd.ldap[0]", provider="sssd.ldap[0]", nfs="sssd.nfs[0]", kdc="sssd.kdc[0]"
        ),
    )

    IPA = SSSDTopologyMark(
        name="ipa",
        topology=Topology(TopologyDomain("sssd", client=1, ipa=1, nfs=1)),
        controller=IPATopologyController(),
        domains=dict(test="sssd.ipa[0]"),
        fixtures=dict(
            client="sssd.client[0]", ipa="sssd.ipa[0]", provider="sssd.ipa[0]", nfs="sssd.nfs[0]"
        ),
    )

    AD = SSSDTopologyMark(
        name="ad",
        topology=Topology(TopologyDomain("sssd", client=1, ad=1, nfs=1)),
        controller=ADTopologyController(),
        domains=dict(test="sssd.ad[0]"),
        fixtures=dict(
            client="sssd.client[0]", ad="sssd.ad[0]", provider="sssd.ad[0]", nfs="sssd.nfs[0]"
        ),
    )

    Samba = SSSDTopologyMark(
        name="samba",
        topology=Topology(TopologyDomain("sssd", client=1, samba=1, nfs=1)),
        controller=SambaTopologyController(),
        domains={"test": "sssd.samba[0]"},
        fixtures=dict(
            client="sssd.client[0]", samba="sssd.samba[0]", provider="sssd.samba[0]", nfs="sssd.nfs[0]"
        ),
    )

.. note::

    Notice that SSSD is using custom topology marker ``SSSDTopologyMark`` that
    adds a custom ``domains`` property. You can see its definition
    `here <sssd_framework_mark_>`_.

If we run the test, we can see that it is executed four times:

.. code-block:: console

    $ pytest --mh-config=mhc.yaml -k test_id -v
    ...
    tests/test_id.py::test_id__supplementary_groups (samba) PASSED                                                                                                                                                                                [ 12%]
    tests/test_id.py::test_id__supplementary_groups (ad) PASSED                                                                                                                                                                                   [ 25%]
    tests/test_id.py::test_id__supplementary_groups (ipa) PASSED                                                                                                                                                                                  [ 37%]
    tests/test_id.py::test_id__supplementary_groups (ldap) PASSED

.. note::

    It is also possible to combine topology parametrization with
    ``@pytest.mark.parametrize``.

    .. code-block:: python

        @pytest.mark.parametrize("value", [1, 2])
        @pytest.mark.topology(KnownTopologyGroup.AnyProvider)
        def test_example(client: Client, provider: GenericProvider, value: int):
            pass

.. _pytest-parametrize: https://docs.pytest.org/en/latest/how-to/parametrize.html#pytest-mark-parametrize-parametrizing-test-functions
.. _sssd: https://sssd.io
.. _sssd_framework_topology: https://github.com/SSSD/sssd-test-framework/blob/0b213ff8fca10a5de55f34f7f2bc94cdba4a3487/sssd_test_framework/topology.py#L138
.. _sssd_framework_mark: https://github.com/SSSD/sssd-test-framework/blob/0b213ff8fca10a5de55f34f7f2bc94cdba4a3487/sssd_test_framework/config.py#L22
