pytest_mh - pytest multihost test framework
###########################################

.. warning::

    This plugin is still actively developed and even though it is mostly stable,
    we reserve the right to introduce minor breaking changes if it is required
    for new functionality. Therefore we advice to pin pytest-mh version for your
    project.

``pytest-mh`` is a multihost testing pytest framework that you can use to **test
your application as a complete product**. One of the core features of this
plugin is to **define set of hosts that are required by your tests** and
**execute commands on these hosts over SSH, podman or docker** while pytest is
run locally and your **local machine is kept intact**. This plugin was designed
especially for a scenario where your application requires multiple hosts to work
(for example a client/server model), but it can be perfectly used for single
host applications as well. The plugin also provides many building blocks that
can help you build a high-level test framework API for your project, including
full backup and restore support. The tests are written in Python, using the
pytest runner, but **your application can be written in any language**.

.. note::

  pytest-mh plugin is designed to test your project as a full product, which is
  often referred to as **system, application or black-box testing**, when your
  project is installed on a host and system commands are run in order to test
  its functionality. **It is not designed for unit testing.**

What are the core features of pytest-mh?
========================================

* Define what hosts are required to run a test. If any of required host is not
  available, the test is skipped. :doc:`articles/extending/multihost-topologies`
* Run commands on remote hosts or containers via SSH, podman or docker.
  :doc:`articles/running-commands`
* Run single test against multiple backends: :ref:`topology_parametrization`
* Write high-level API for your testing framework: :doc:`articles/extending`
* Extensive custom setup and teardown logic with various setup/teardown hooks: :doc:`articles/life-cycle/setup-and-teardown`
* Automatic static and dynamic artifacts collection: :doc:`articles/life-cycle/artifacts-collection`
* Automatic change test result based on additional conditions: :doc:`articles/life-cycle/changing-test-status`
* Skip tests if the hosts are missing any required features: :doc:`articles/life-cycle/skipping-tests`
* Automatic backup and restore of hosts state: :doc:`articles/tips-and-tricks/backup-restore`
* Out of the box: write and read files and other file system operations with automatic changes reversion: :doc:`articles/bundled-utilities/fs`
* Out of the box: start, stop and manage systemd services: :doc:`articles/bundled-utilities/services`
* Out of the box: manipulate system firewall: :doc:`articles/bundled-utilities/firewall`
* Out of the box: auto detection of AVC denials: :doc:`articles/bundled-utilities/auditd`
* Out of the box: auto detection of coredumps: :doc:`articles/bundled-utilities/coredumpd`
* Out of the box: check journald logs: :doc:`articles/bundled-utilities/journald`
* Out of the box: delay network traffic: :doc:`articles/bundled-utilities/tc`

Do I want to use pytest-mh?
===========================

* **Does your program affect the host in any way?** If yes, it is safer to run
  it in virtual machine or in a container to avoid affecting your local host.
  ``pytest-mh`` takes care of that.
* **Does your program use client-server model?** If yes, it is better to run the
  client and the server on separate machines to make the tests more real.
  ``pytest-mh`` takes care of that.
* **Does your program communicate with multiple backends?** If yes, you need to
  be able to assign each test to a specific backend and also be able to reuse a
  single test for multiple backends. ``pytest-mh`` takes care of that.
* **Do you need complex tests that changes state of the system, file system or
  other programs or databases?** If yes, you need to make sure that all changes
  are reverted when a test is done so the test does not affect other tests.
  ``pytest-mh`` takes care of that.

.. code-block:: python
    :caption: Example test taken from SSSD project

    @pytest.mark.topology(KnownTopology.AD)
    @pytest.mark.topology(KnownTopology.LDAP)
    @pytest.mark.topology(KnownTopology.IPA)
    @pytest.mark.topology(KnownTopology.Samba)
    def test_id(client: Client, provider: GenericProvider):
        u = provider.user("tuser").add()
        provider.group("tgroup_1").add().add_member(u)
        provider.group("tgroup_2").add().add_member(u)

        client.sssd.start()
        result = client.tools.id("tuser")

        assert result is not None
        assert result.user.name == "tuser"
        assert result.memberof(["tgroup_1", "tgroup_2"])

.. seealso::

    This project was originally created for `SSSD <https://sssd.io>`__ and you
    can use `sssd-test-framework
    <https://github.com/SSSD/sssd-test-framework>`__ (built on top of pytest-mh)
    and `the sssd tests
    <https://github.com/SSSD/sssd/tree/master/src/tests/system>`__ for
    inspiration.

Table of Contents
=================

.. toctree::
    :maxdepth: 2

    articles/get-started
    articles/extending
    articles/life-cycle
    articles/bundled-utilities
    articles/running-commands
    articles/mhc-yaml
    articles/writing-tests
    articles/running-tests
    articles/tips-and-tricks
    api
