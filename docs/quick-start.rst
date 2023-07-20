Quick Start Guide
#################

This guide will show you how to setup and extend the ``pytest-mh`` plugin. We will
write a simple test of Kerberos authentication that spans over two separate
hosts - one host has the Kerberos KDC running and the other host will be used as
a client machine.

.. note::

    The complete code is located in the `example
    <https://github.com/next-actions/pytest-mh/tree/master/example>`__ directory
    of `pytest-mh <https://github.com/next-actions/pytest-mh>`__ repository.

.. seealso::

    A real life example of how ``pytest-mh`` can help to test your code can be
    seen in the `SSSD
    <https://github.com/SSSD/sssd/tree/master/src/tests/system>`__ project.

All projects are different, therefore :mod:`pytest_mh` plugin provides only the
most basic functionality like ``ssh`` access to hosts and building blocks to
build your own tools and API. It is expected that you implement required
functionality in host, role and utility classes by extending
:class:`~pytest_mh.MultihostHost`, :class:`~pytest_mh.MultihostRole` and
:class:`~pytest_mh.MultihostUtility`.

Since :mod:`pytest_mh` plugin is fully extensible, it is possible to also add
your own configuration options and different domain types by extending
:class:`~pytest_mh.MultihostConfig` and :class:`~pytest_mh.MultihostDomain`.
This step is actually required as the base classes are abstract and you have to
overwrite specific methods and properties in order to give a list of your own
domain, host and role classes that will be automatically be instantiated by the
plugin.

.. note::

    The difference between host, roles, and utility classes:

    * Host classes are created only once before the first test is executed and
      exist during the whole pytest session. They can be used to setup
      everything that should live for the whole session.
    * Role classes are the main objects that are directly accessible from
      individual tests. They are created just before the test execution and
      destroyed once the test is finished. They can perform setup required to
      run the tests and proper clean up after the test is finished. Roles should
      also define and implement proper API to access required resources.
    * Utility classes are instantiated inside individual roles. They represent
      functionality that can be shared between roles. They are also responsible
      to clean up every change that is done through their API. The
      :mod:`pytest_mh` plugin already has some utility classes bundled within,
      see :mod:`pytest_mh.utils`.

Create configuration and domain classes
=======================================

First of all, we need to extend :class:`~pytest_mh.MultihostConfig` and tell it
how to create our own domain object. Additionally, we need to extend
:class:`~pytest_mh.MultihostDomain` and define a mapping between role name and
host classes and also a mapping between role name and role classes. This tells
the plugin which host and role classes should be instantiated for given role.

In the example below, we define two roles: "client" and "kdc". Each role has its
own role (``client``, ``KDC``) and host class (``ClientHost``, ``KDCHost``).

.. literalinclude:: ../example/lib/config.py
    :caption: /lib/config.py
    :emphasize-lines: 9-10, 14-27, 29-42
    :language: python
    :linenos:

.. note::

    It is not necessary to create distinct role and host class for every role.
    The classes can be shared for multiple roles if it makes sense for your
    project.

Create host classes
===================

KDC Host
********

The KDC host takes care of backup and restore of the KDC data. It create backup
of KDC database when pytest is started and restores it to the original state
every time a test is finished. This ensures that the database is always the same
for each test execution. It also removes the backup file when pytest is
terminated.

.. literalinclude:: ../example/lib/hosts/kdc.py
    :caption: /lib/hosts/kdc.py
    :language: python
    :emphasize-lines: 33-34, 40-45, 54
    :linenos:

Client Host
***********

The client host does not perform any backup and restore as it is not needed, but
it reads additional configuration values from the multihost configuration
(``mhc.yaml``) file.

.. note::

    The additional configuration is read from the standard ``config`` field
    which is there for this very reason. But if it makes sense, you can of
    course extend any section.

.. literalinclude:: ../example/lib/hosts/client.py
    :caption: /lib/hosts/client.py
    :emphasize-lines: 37-39
    :language: python
    :linenos:

Create role classes
===================

Unlike hosts, the role classes are the right place to provide all functionality
that will help you write good tests so they are usually quite complex.

KDC Role
********

The ``KDC`` class implements the functionality desired for "kdc" role. In this
example, we focus on adding the Kerberos principal (or *Kerberos user* if you
are not familiar with Kerberos terminology) and querying the kadmin tool to get
some additional information.

.. literalinclude:: ../example/lib/roles/kdc.py
    :caption: /lib/roles/kdc.py
    :language: python
    :linenos:

Client Role
***********

The client role first creates ``/etc/krb5.conf`` so the Kerberos client knows
what KDC we want to use. For this, it uses the bundle
:class:`~pytest_mh.utils.fs.LinuxFileSystem` utility class, which writes the file to
the remote path and when a test is finished, it makes sure to restore the
original content or remove the file if it was not present before.

.. literalinclude:: ../example/lib/roles/client.py
    :caption: /lib/roles/client.py
    :language: python
    :emphasize-lines: 35, 82
    :linenos:

Define multihost topology
=========================

Each test is associated with one or more topologies. A topology defines multihost
requirements that must be met in order to run the test. If the requirements are
not met, the test will not run. These requirements are:

* What domains are available
* What roles and how many roles inside each domain are available

To assign a topology to a test case, we use ``@pytest.mark.topology(...)``. The
next example defines a topology with one domain that contains one client and one
kdc role. Hosts that implements these roles are then available as pytest
fixtures.

.. code-block:: python

    @pytest.mark.topology(
        "kdc", Topology(TopologyDomain("test", client=1, kdc=1)),
        client="test.client[0]", kdc="test.kdc[0]"
    )
    def test_example(client: Client, kdc: KDC):
        pass

However, this can be little bit cumbersome, therefore it is good practice to
define a list of known topologies first.

.. literalinclude:: ../example/lib/topology.py
    :caption: /lib/topology.py
    :language: python
    :emphasize-lines: 25-29
    :linenos:

Now we can shorten the topology marker like this:

.. code-block:: python

    @pytest.mark.topology(KnownTopology.KDC)
    def test_example(client: Client, kdc: KDC):
        pass

.. seealso::

    There is also :class:`~pytest_mh.KnownTopologyGroupBase` to define a list of
    topologies that should be assigned to the test case and thus create topology
    parameterization.

Create multihost configuration
==============================

Now, our test framework is ready to use. We just need to provide multihost
configuration file that defines available hosts.

We set custom fields that are required by ``ClientHost`` and we also define list
of artifacts that are automatically fetched from the remote host.

.. literalinclude:: ../example/mhc.yaml
    :caption: /mhc.yaml
    :language: yaml
    :emphasize-lines: 6-9, 13-14
    :linenos:

.. note::

    The example configuration assumes running containers from
    `sssd-ci-containers <https://github.com/SSSD/sssd-ci-containers>`__ project.

Enable pytest-mh in pytest
==========================

The ``pytest-mh`` plugin needs to be manually enabled in ``conftest.py`` and it
needs to know the configuration class that should be instantiated.

.. literalinclude:: ../example/conftest.py
    :caption: /conftest.py
    :language: python
    :emphasize-lines: 10, 14-16
    :linenos:

Write and run a simple test
===========================

All the pieces are now available. We have successfully setup the ``pytest-mh``
plugin, created our own test framework API. Now it is time to write some tests.

.. literalinclude:: ../example/tests/test_kdc.py
    :caption: /tests/test_kdc.py
    :language: python
    :emphasize-lines: 9-10, 20-21
    :linenos:

Now we can run them. Notice how the topology name is mentioned in the test name.

.. code-block:: text

    $ pytest --mh-config=./mhc.yaml -vv
    Multihost configuration:
    domains:
    - id: test
        hosts:
        - hostname: client.test
          role: client
          config:
            realm: TEST
            krbdomain: test
            kdc: kdc.test
        - hostname: kdc.test
          role: kdc
          artifacts:
          - /var/log/krb5kdc.log

    Detected topology:
    - id: test
        hosts:
        client: 1
        kdc: 1

    Additional settings:
    config file: ./mhc.yaml
    log path: None
    lazy ssh: False
    topology filter: None
    require exact topology: False
    collect artifacts: on-failure
    artifacts directory: ./artifacts

    ============================================================================================================ test session starts =============================================================================================================
    platform linux -- Python 3.10.8, pytest-7.2.1, pluggy-1.0.0 -- /home/pbrezina/workspace/pytest-mh/.venv/bin/python3
    cachedir: .pytest_cache
    rootdir: /home/pbrezina/workspace/pytest-mh, configfile: pytest.ini
    collected 2 items

    tests/test_kdc.py::test_kinit (kdc) PASSED                                                                                                                                                                                             [ 50%]
    tests/test_kdc.py::test_kvno (kdc) PASSED

