Getting Started
###############

Pytest-mh is not a plugin to support unit testing. It is a plugin designed to
support testing your application as a complete product, this is often referred
to as a black-box, application or system testing. The application is installed
on the target host and tested by running commands on the host (and on other
hosts that are required). These hosts can be virtual machines or containers.

.. seealso::

    SSH, podman and docker may be used to execute commands on the remote hosts. See
    :doc:`running-commands` for more information.

As such, it is often useful to write a high level API that will support testing
your application and make your test smaller and more readable. This may require
a non-trivial initial investment, but it will pay off in the long run. However,
implementing such API is not required and it is perfectly possible to run
commands on the host directly from each test. This approach makes tests usually
larger and more difficult to understand and maintain -- but every project is
different and it is up to you to choose how are you going to test your
application.

.. seealso::

    Pytest-mh provides several building blocks to help you design your test
    framework. See :doc:`extending`. **It would be good to open this document
    and read it side by side.**

We will use `sudo <https://www.sudo.ws/>`__ as the application to test for this
getting started guide as sudo is known by every power user so chances are that
you are already familiar with it. Additionally, sudo tests allows us to show
many pytest-mh features. Note, that these tests were written only as an example
and sudo itself is not using pytest-mh for its tests at this moment and as far
as we know there are no plans to do so.

.. seealso::

    The example code can be found in the `example
    <https://github.com/next-actions/pytest-mh/tree/master/example>`__ folder of
    the git repository.

Example project: sudo
=====================

`Sudo <https://www.sudo.ws/>`__ is a widely known tool that can elevate current
user's privileges by running command as different user -- usually ``root``. It
is possible to write a set of rules to define which user can run which command
and these rules can be stored either locally in ``/etc/sudoers`` or in `LDAP
<https://en.wikipedia.org/wiki/Lightweight_Directory_Access_Protocol>`__
database.

Our goals are:

* write basic tests

  * allow the user to run all commands, user must authenticate
  * allow the user to run all commands, without authentication
  * allow the user to run all commands if they are a member of a group, user
    must authenticate
  * allow the user to run all commands if they are a member of a group, without
    authentication

* these tests must be written for all possible sources of data

  * file: ``/etc/sudoers``
  * LDAP pulled directly by sudo
  * LDAP pulled by SSSD

* write a simple test framework that will help us to extend the tests easily
* every change must be reverted after each test

As you can see, these goals require us to write 12 tests in total. But since the
result is the same and only the data is fetched from different sources, we can
use :ref:`topology parametrization <topology_parametrization>`. Topology
parametrization allows us to write only one test but run it against
different backends and thus we will do less work but get more code coverage.

We will take the following steps to achieve it:

#. :ref:`get_started_structure`
#. :ref:`get_started_topologies`
#. :ref:`get_started_config_file`
#. :ref:`get_started_config_domain`
#. :ref:`get_started_framework`
#. :ref:`get_started_enable`
#. :ref:`get_started_write_tests`
#. :ref:`get_started_run_tests`

.. _get_started_structure:

Prepare a file structure
------------------------

The following snippet shows a recommended file structure for your test utilizing
pytest-mh. Look at :doc:`extending` to get more information about the meaning of
individual classes.

.. code-block:: text

    .
    ├── framework/                    # Test framework, high-level API
    │   ├── hosts/                    # Subclasses of MultihostHost
    │   │   └── __init__.py
    │   ├── roles/                    # Subclasses of MultihostRole
    │   │   └── __init__.py
    │   ├── utils/                    # Subclasses of MultihostUtility
    │   │   └── __init__.py
    │   ├── __init__.py
    │   ├── config.py                 # Definition of MultihostConfig, MultihostDomain
    │   ├── topology_controllers.py   # Custom topology controllers
    │   └── topology.py               # Definition of multihost topologies
    |
    ├── tests/                        # Tests
    |
    ├── conftest.py                   # Pytest conftest.py
    ├── pytest.ini                    # Pytest configuration file
    ├── py.typed                      # Declare that this project uses type hints
    |
    ├── mhc.yaml                      # Pytest-mh configuration file
    |
    ├── readme.md                     # Tests readme
    └── requirements.txt              # Tests requirements

.. _get_started_topologies:

Define multihost topologies
---------------------------

This is the first step when designing a test framework since it defines what
hosts and roles your project needs. For sudo, we want sudo rules to be fetched
from different sources. We can consider each data source to be a single
topology.

* **sudoers**

  * only one host needed
  * users, groups and sudo rules will be created locally

* **ldap**

  * we need a host where we will run sudo and a host that runs an LDAP server
  * users, groups and sudo rules will be added to the LDAP database
  * sudo will read data from LDAP

* **sssd**

  * we need a host where we will run sudo and SSSD and a host that runs an LDAP server
  * SSSD will be connected to the LDAP domain
  * users, groups and sudo rules will be added to the LDAP database
  * sudo will read data from SSSD which in turn reads it from LDAP

These are the three topologies that we will define. We will also define a
topology group as a shortcut for :ref:`topology parametrization
<topology_parametrization>`.

.. dropdown:: See the code
    :color: primary
    :icon: code

    .. tab-set::

        .. tab-item:: ./framework/topology.py

            .. literalinclude:: ../../example/framework/topology.py
                :language: python

.. _get_started_config_file:

Write configuration file
------------------------

The topology defines which hosts and roles are needed to run sudo tests. We can
convert it into a configuration file that can be used to run all sudo tests.

The configuration file will define one domain with two hosts - one ``client``
which will run sudo and SSSD and one ``ldap`` which will run the LDAP server.

.. seealso::

    The full format of the configuration file can be found at :doc:`mhc-yaml`.

.. dropdown:: See the code
    :color: primary
    :icon: code

    .. tab-set::

        .. tab-item:: ./mhc.yml

            .. literalinclude:: ../../example/mhc.yaml
                :language: yaml

.. _get_started_config_domain:

Define :class:`~pytest_mh.MultihostConfig` and :class:`~pytest_mh.MultihostDomain`
----------------------------------------------------------------------------------

These two classes are required to correctly map the configuration file into your
Python code. Look for more information at :doc:`extending/multihost-config` and
:doc:`extending/multihost-domains`. It is possible to extend these classes in
order to add custom configuration options, use different topology mark and so
on. In this example, they only provide the mapping from configuration file to
Python classes.

.. dropdown:: See the code
    :color: primary
    :icon: code

    .. tab-set::

        .. tab-item:: ./framework/config.py

            .. literalinclude:: ../../example/framework/config.py
                :language: python

.. _get_started_framework:

Design and implement the framework
----------------------------------

This step is more complicated and can not be treated universally as every
project has different needs. It is possible to use multiple building blocks
provided by ``pytest-mh`` in order to build a high-level API for your tests, see
:doc:`extending` and :doc:`life-cycle` to get a good grasp of all the classes
and how to use them.

For the sudo tests, we have implemented several hosts, roles and utility classes
and one topology controller for each topology. The following table describes the
main idea behind each of these classes.

.. dropdown:: See the table
    :color: primary
    :icon: code

        .. list-table::
            :header-rows: 1

            * - Class name/Subclass of
              - Description

            * - | ``ClientHost``
                | :class:`~pytest_mh.MultihostBackupHost`
              - * Implements backup and restore methods for the client.

            * - | ``LDAPHost``
                | :class:`~pytest_mh.MultihostBackupHost`
              - * Implements backup and restore methods for the LDAP server.
                * Opens and maintains connection to the LDAP server using
                  python-ldap library.

            * - | ``SudoersTopologyController``
                | :class:`~pytest_mh.BackupTopologyController`
              - * Configures environment for the sudoers topology
                * Sets expected content of ``/etc/nsswitch.conf``
                * Creates backup of this setup and automatically restores its
                  state when a test is finished

            * - | ``LDAPTopologyController``
                | :class:`~pytest_mh.BackupTopologyController`
              - * Configures environment for the LDAP topology
                * Sets expected content of ``/etc/nsswitch.conf``
                * Configures SSSD for identity and authentication
                * Configures ``/etc/ldap.conf`` that is read by sudo
                * Creates backup of this setup and automatically restores its
                  state when a test is finished

            * - | ``SSSDTopologyController``
                | :class:`~pytest_mh.BackupTopologyController`
              - * Configures environment for the SSSD topology
                * Sets expected content of ``/etc/nsswitch.conf``
                * Configures SSSD for identity, authentication and sudo rules
                * Creates backup of this setup and automatically restores its
                  state when a test is finished

            * - | ``Client``
                | :class:`~pytest_mh.MultihostRole`
              - * Implements ``GenericProvider`` which defines interface for
                  managing users, groups and sudoers.
                * The implementation uses local files to store the content.

            * - | ``LDAP``
                | :class:`~pytest_mh.MultihostRole`
              - * Implements ``GenericProvider`` which defines interface for
                  managing users, groups and sudoers.
                * The implementation uses LDAP to store the content.

            * - | ``LocalUsersUtils``
                | :class:`~pytest_mh.MultihostUtility`
              - * Provides shareable implementation of local users and groups
                  management.
                * Every user and group added during testing is automatically
                  removed.

            * - | ``SUDOUtils``
                | :class:`~pytest_mh.MultihostUtility`
              - * Implements methods to execute sudo and assert the result

.. seealso::

    Look at the `example code
    <https://github.com/next-actions/pytest-mh/tree/master/example>`__ to see
    how this was implemented.

.. _get_started_enable:

Enable pytest-mh in conftest.py
-------------------------------

When the test framework is written and ready to use, we can tell pytest to
start using it in our tests. First, configure pytest to load pytest-mh plugin and
then inform pytest-mh which config class it should instantiate.

.. dropdown:: See the code
    :color: primary
    :icon: code

    .. tab-set::

        .. tab-item:: ./conftest.py

            .. literalinclude:: ../../example/conftest.py
                :language: python

.. _get_started_write_tests:

Write the tests
===============

The example code shows four tests in total, but 12 tests are executed when
pytest is run because each test is run once per topology against different data
sources. See :doc:`writing-tests` to get more information on how to write
the tests.

  * allow the user to run all commands, user must authenticate
  * allow the user to run all commands, without authentication
  * allow the user to run all commands if they are a member of a group, user
    must authenticate
  * allow the user to run all commands if they are a member of a group, without
    authentication

.. dropdown:: See the code
    :color: primary
    :icon: code

    .. tab-set::

        .. tab-item:: ./tests/test_user.py

            .. literalinclude:: ../../example/tests/test_user.py
                :language: python

        .. tab-item:: ./tests/test_group.py

            .. literalinclude:: ../../example/tests/test_group.py
                :language: python

.. _get_started_run_tests:

Run the tests
=============
The example code provides a set of containers that can be started and used as
hosts for testing. See the example `readme.md
<https://github.com/next-actions/pytest-mh/tree/master/example/readme.md>`__ to
get the instruction on how to start the containers and install requirements.

When the containers or virtual machines are ready, it is possible to run the
tests with the ``pytest`` command that you are already familiar with. The only
additional thing needed to run pytest-mh tests is to provide the path to the
pytest-mh configuration file with ``--mh-config``.

.. code-block:: text

    $ pytest --color=yes --mh-config=./mhc.yaml -vvv

    Multihost configuration:
      domains:
      - id: sudo
        hosts:
        - hostname: master.ldap.test
          conn:
            type: ssh
            host: 172.16.200.3
          role: ldap
        - hostname: client.test
          conn:
            type: ssh
            host: 172.16.200.4
          role: client
          artifacts:
          - /var/log/sssd

    Detected topology:
      - id: sudo
        hosts:
          ldap: 1
          client: 1

    Additional settings:
      config file: ./example/mhc.yaml
      log path: None
      lazy ssh: False
      topology filter:
      require exact topology: False
      collect artifacts: on-failure
      artifacts directory: artifacts
      collect logs: on-failure

    ============================= test session starts ==============================
    platform linux -- Python 3.11.9, pytest-8.3.3, pluggy-1.5.0 -- /home/runner/work/pytest-mh/pytest-mh/.venv/bin/python3
    cachedir: .pytest_cache
    rootdir: /home/runner/work/pytest-mh/pytest-mh/example
    configfile: pytest.ini
    collecting ...

    Selected tests will use the following hosts:
      client: client.test
      ldap: master.ldap.test

    collected 12 items

    example/tests/test_group.py::test_group__passwd (ldap) PASSED            [  8%]
    example/tests/test_group.py::test_group__nopasswd (ldap) PASSED          [ 16%]
    example/tests/test_user.py::test_user__passwd (ldap) PASSED              [ 25%]
    example/tests/test_user.py::test_user__nopasswd (ldap) PASSED            [ 33%]
    example/tests/test_group.py::test_group__passwd (sssd) PASSED            [ 41%]
    example/tests/test_group.py::test_group__nopasswd (sssd) PASSED          [ 50%]
    example/tests/test_user.py::test_user__passwd (sssd) PASSED              [ 58%]
    example/tests/test_user.py::test_user__nopasswd (sssd) PASSED            [ 66%]
    example/tests/test_group.py::test_group__passwd (sudoers) PASSED         [ 75%]
    example/tests/test_group.py::test_group__nopasswd (sudoers) PASSED       [ 83%]
    example/tests/test_user.py::test_user__passwd (sudoers) PASSED           [ 91%]
    example/tests/test_user.py::test_user__nopasswd (sudoers) PASSED         [100%]

    ============================= 12 passed in 24.80s ==============================
