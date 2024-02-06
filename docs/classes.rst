Extending pytest-mh
###################

There are five main classes that are used by the ``pytest-mh`` plugin that give
you access to remote hosts and provide you tools to build your own API that
fulfills specific requirements.

By extending these classes, you can provide your own functionality and
configuration options.

* :class:`~pytest_mh.MultihostConfig`: top level class that reads configuration and creates domain objects
* :class:`~pytest_mh.MultihostDomain`: creates host objects
* :class:`~pytest_mh.MultihostHost`: lives through the whole pytest session, gives low-level access to the host
* :class:`~pytest_mh.MultihostRole`: lives only for a single test case, provides high-level API
* :class:`~pytest_mh.MultihostUtility`: provides high-level API that can be shared between multiple roles
* :class:`~pytest_mh.TopologyController`: control topology behavior such as per-topology setup and teardown

.. mermaid::
    :caption: Class relationship
    :align: center

    graph LR
        subgraph Lives for the whole pytest session
            MultihostConfig -->|creates| MultihostDomain
            MultihostDomain -->|creates| MultihostHost
        end

        subgraph Lives only for single test case
            mh(mh fixture) -->|creates| MultihostRole
            MultihostRole -->|uses| MultihostHost
            MultihostRole -->|creates| MultihostUtility
        end

In order to start using ``pytest-mh``, you must provide at least your
own::class:`~pytest_mh.MultihostConfig` to define what domain objects will be
created and :class:`~pytest_mh.MultihostDomain` to associate hosts and roles
with specific classes. It is recommended that you also extend the other classes
as well to provide high-level API for your tests.

.. note::

    :class:`~pytest_mh.MultihostHost`, :class:`~pytest_mh.MultihostRole` and
    :class:`~pytest_mh.MultihostUtility` **have setup and teardown methods**
    that you can use to properly initialize the host and also **to clean up**
    after the test is finished.

    By extending these classes, you can give test writers a well-defined,
    unified API that can automate several tasks and make sure the hosts are
    properly setup before the test starts and all changes are correctly reverted
    once the test is finished.

    This makes it easier to write new tests and ensure that the tests start
    with a fresh setup every time.

MultihostConfig
===============

:class:`~pytest_mh.MultihostConfig` is created by ``pytest-mh`` pytest plugin
during pytest session initialization. It reads the given multihost configuration
and creates the domain objects.

You must provide your own class that extends :class:`~pytest_mh.MultihostConfig`
in order to use the plugin. Your class must override
:attr:`~pytest_mh.MultihostConfig.id_to_domain_class` which creates your own
:class:`~pytest_mh.MultihostDomain` object.

Optionally, you can override
:attr:`~pytest_mh.MultihostConfig.TopologyMarkClass` and provide your own
:class:`~pytest_mh.TopologyMark` class. With this, you can provide additional
information to the topology marker as needed by your project.

.. code-block:: python

    class ExampleMultihostConfig(MultihostConfig):
        @property
        def TopologyMarkClass(self) -> Type[TopologyMark]:
            return ExampleTopologyMark

        @property
        def id_to_domain_class(self) -> dict[str, Type[MultihostDomain]]:
            """
            Map domain id to domain class. Asterisk ``*`` can be used as fallback
            value.

            :rtype: Class name.
            """
            return {"*": ExampleMultihostDomain}

MultihostDomain
===============

:class:`~pytest_mh.MultihostDomain` is created by
:class:`~pytest_mh.MultihostConfig` and it allows you to associate roles from
your multihost configuration to your own hosts, roles, and Python classes to give
them meaning.

.. code-block:: python

    class ExampleMultihostDomain(MultihostDomain[ExampleMultihostConfig]):
        def __init__(self, config: ExampleMultihostConfig, confdict: dict[str, Any]) -> None:
            super().__init__(config, confdict)

        @property
        def role_to_host_class(self) -> dict[str, Type[MultihostHost]]:
            """
            Map role to host class. Asterisk ``*`` can be used as fallback value.

            :rtype: Class name.
            """
            return {
                "client": ClientHost,
                "ldap": LDAPHost,
            }

        @property
        def role_to_role_class(self) -> dict[str, Type[MultihostRole]]:
            """
            Map role to role class. Asterisk ``*`` can be used as fallback value.

            :rtype: Class name.
            """
            return {
                "client": Client,
                "ldap": LDAP,
            }

MultihostHost
=============

One :class:`~pytest_mh.MultihostHost` object is created per each host defined in
your multihost configuration. Each host is created as an instance of a class
that is determined by the role to host mapping in
:meth:`~pytest_mh.MultihostDomain.role_to_host_class`.

This object gives you access to a SSH connection to the remote host. The object
lives for the whole pytest session which makes it a good place to put
functionality and data that must be available across all tests. For example, it
can perform an initial backup of the host.

It provides two setup and teardown methods:

* :meth:`~pytest_mh.MultihostHost.pytest_setup` - called when pytest starts before execution of any test
* :meth:`~pytest_mh.MultihostHost.pytest_teardown` - called when pytest terminated after all tests are done
* :meth:`~pytest_mh.MultihostHost.setup` - called before execution of each test
* :meth:`~pytest_mh.MultihostHost.teardown` - called after a test is done

.. seealso::

    See `/example/lib/hosts/kdc.py
    <https://github.com/next-actions/pytest-mh/blob/master/example/lib/hosts/kdc.py>`__
    to see an example implementation of custom host.

MultihostRole
=============

Similar to :class:`~pytest_mh.MultihostHost`, one
:class:`~pytest_mh.MultihostRole` object is created per each host defined in
your multihost configuration. The difference between these two is that while
:class:`~pytest_mh.MultihostHost` lives for the whole pytest session,
:class:`~pytest_mh.MultihostRole` lives only for a single test run therefore the
role objects are not shared between tests. Role objects are also available to
you in your tests through pytest dynamic fixtures.

The purpose of the :class:`~pytest_mh.MultihostRole` object is to provide high
level API for your project that you can use in your tests and to perform
per-test setup and clean up. For this purpose, it provides setup and teardown
methods that you can overwrite:

* :meth:`~pytest_mh.MultihostRole.setup` - called before execution of each test
* :meth:`~pytest_mh.MultihostRole.teardown` - called after a test is done

.. seealso::

    See `/example/lib/roles/kdc.py
    <https://github.com/next-actions/pytest-mh/blob/master/example/lib/roles/kdc.py>`__
    to see an example implementation of custom role.

MultihostUtility
================

Role object can also contain instances of :class:`~pytest_mh.MultihostUtility`
that can be used to share functionality between individual roles. A
:meth:`~pytest_mh.MultihostUtility.setup` and
:meth:`~pytest_mh.MultihostUtility.teardown` methods are automatically called
after the role is setup and before the role teardown is executed.

.. note::

    :class:`~pytest_mh.MultihostUtility` also contains
    :meth:`~pytest_mh.MultihostUtility.setup_when_used` which is called only
    after the class is first used inside the test (after
    :meth:`~pytest_mh.MultihostUtility.setup`) and
    :meth:`~pytest_mh.MultihostUtility.teardown_when_used` which is called only
    if the class was used (before :meth:`~pytest_mh.MultihostUtility.teardown`).

    This can be especially useful if the utility class is used only sporadically
    but the setup and teardown are quite expensive. In such case, you probably
    want to perform the setup and teardown only if the class was actually used
    in the test.

There are already some utility classes implemented in ``pytest-mh``. See
:mod:`pytest_mh.utils` for more information on them.

.. seealso::

    See `/pytest_mh/utils/fs.py
    <https://github.com/next-actions/pytest-mh/blob/master/pytest_mh/utils/fs.py>`__
    to see an implementation of a utility class that gives you access to files
    and directories on the remote host.

    Each change that is made through the utility object (such as writing to a
    file) is automatically reverted (the original file is restored).

TopologyController
==================

Topology controller can be assigned to a topology via `@pytest.mark.topology`
or through known topology class. This controller provides various methods to
control the topology behavior:

* per-topology setup and teardown, called once before the first test/after the
  last test for given topology is executed
* per-test topology setup and teardown, called before and after every test case
  for given topology
* check topology requirements and skip the test if these are not satisfied

In order to use the controller, you need to inherit from
:class:`~pytest_mh.TopologyController` and override desired methods. Each method
can take any parameter as defined by the topology fixtures. The parameter value
is an instance of a :class:`~pytest_mh.MultihostHost` object.

See :class:`~pytest_mh.TopologyController` for API documentation

.. code-block:: python
    :caption: Example topology controller

    class ExampleController(TopologyController):
        def skip(self, client: ClientHost) -> str | None:
            result = client.ssh.run(
                '''
                # Implement your requirement check here
                exit 1
                ''', raise_on_error=False)
            if result.rc != 0:
                return "Topology requirements were not met"

            return None

        def topology_setup(self, client: ClientHost):
            # One-time setup, prepare the host for this topology
            # Changes done here are shared for all tests
            pass

        def topology_teardown(self, client: ClientHost):
            # One-time teardown, this should undo changes from
            # topology_setup
            pass

        def setup(self, client: ClientHost):
            # Perform per-topology test setup
            # This is called before execution of every test
            pass

        def teardown(self, client: ClientHost):
            # Perform per-topology test teardown, this should undo changes
            # from setup
            pass

.. code-block:: python
    :caption: Example with low-level topology mark

    class ExampleController(TopologyController):
        # Implement methods you are interested in here
        pass

    @pytest.mark.topology(
        "example", Topology(TopologyDomain("example", client=1)),
        controller=ExampleController(),
        fixtures=dict(client="example.client[0]")
    )
    def test_example(client: Client):
        pass

.. code-block:: python
    :caption: Example with KnownTopology (recommended)

    class ExampleController(TopologyController):
        # Implement methods you are interested in here
        pass

    @final
    @unique
    class KnownTopology(KnownTopologyBase):
        EXAMPLE = TopologyMark(
            name='example',
            topology=Topology(TopologyDomain("example", client=1)),
            controller=ExampleController(),
            fixtures=dict(client='example.client[0]'),
        )

    @pytest.mark.topology(KnownTopology.EXAMPLE)
    def test_example(client: Client):
        pass

.. _setup-and-teardown:

Setup and teardown
==================

The following schema shows how individual setup and teardown methods of host,
role, and utility objects are executed.

.. mermaid::
    :caption: Setup and teardown
    :align: center

    graph TD
        s([start]) --> hps(host.pytest_setup)

        subgraph run [ ]
            subgraph setup [Setup before test]
                hs(host.setup) --> cs(controller.setup) --> rs[role.setup]
                rs --> us[utility.setup]
            end

            setup -->|run test| teardown

            subgraph teardown [Teardown after test]
                ut[utility.teadown] --> rt[role.teardown]
                rt --> ct(controller.teardown)
                ct --> ht(host.teardown)
            end
        end

        hps -->|run tests| cts(controller.topopology_setup) -->|run all tests for topology| run
        run -->|all tests for topology finished| ctt(controller.topology_teardown) -->|all tests finished| hpt(host.pytest_teardown)
        hpt --> e([end])

        style run fill:#FFF
        style setup fill:#DFD,stroke-width:2px,stroke:#AFA
        style teardown fill:#FDD,stroke-width:2px,stroke:#FAA
