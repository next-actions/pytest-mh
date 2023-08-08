pytest_mh - pytest multihost test framework
###########################################

``pytest-mh`` is a pytest plugin that, at a basic level, allows you to run shell
commands and scripts over SSH on remote Linux or Windows hosts. You use it to
execute system or application tests for your project on a remote host or hosts
(or containers) while running pytest locally keeping your local machine intact.

The plugin also provides building blocks that can be used to setup and teardown
your tests, perform automatic clean up of all changes done on the remote host,
and build a flexible and unified high-level API to manipulate the hosts from
your tests.

.. code-block:: python
    :caption: Example test taken from SSSD demo

    @pytest.mark.topology(KnownTopology.AD)
    @pytest.mark.topology(KnownTopology.LDAP)
    @pytest.mark.topology(KnownTopology.IPA)
    @pytest.mark.topology(KnownTopology.Samba)
    def test__id(client: Client, provider: GenericProvider):
        u = provider.user("tuser").add()
        provider.group("tgroup_1").add().add_member(u)
        provider.group("tgroup_2").add().add_member(u)

        client.sssd.start()
        result = client.tools.id("tuser")

        assert result is not None
        assert result.user.name == "tuser"
        assert result.memberof(["tgroup_1", "tgroup_2"])

.. seealso::

    A real life example of how ``pytest-mh`` can help test your code can be
    seen in the `SSSD
    <https://github.com/SSSD/sssd/tree/master/src/tests/system>`__ project.

When do I want use the framework?
*********************************

* **Does your program affect the host in any way?** If yes, it is safer to run it in
  virtual machine or in a container to avoid affecting your local host.
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
* Does your program **talk to LDAP/IPA/AD/Samba/Kerberos**? If yes, ``pytest-mh``
  can help you with that.
* **Do you use** `pytest-multihost
  <https://pypi.org/project/pytest-multihost/>`__ **framework for your current
  tests?** ``pytest-mh`` is a full Python 3 re-implementation of the old
  ``pytest-multihost`` plugin. It builds on all its features and takes it to
  a whole new level. You definitely want to switch to ``pytest-mh``,
  however it is not backwards compatible.

When I don't want to use it?
****************************

* Do you want to test your Python code? Then this plugin will not help
  you. It is designed for running system or applications tests, i.e. testing
  your application as a whole.

What does the framework do?
***************************

* Allows you to **run commands over SSH on remote hosts** (or virtual machines or
  containers) using bash or Powershell.
* Allows you to **define your own roles with a provide fully typed API** to your
  tests that fulfills all your needs.
* All **changes that you do on the remote host during a single test can be
  completely reverted** so they do not affect other tests.
* Defines an available **multihost topology** - what roles are available in your
  current setup.
* **Associates each test with certain topology** - defines what roles are
  required to run the test.
* Supports **topology parametrization** - a single test can run on multiple
  topologies.
* **Run only tests that can be run on available topology**.
* Provides **access to roles through dynamic pytest fixtures**.
* **The code is fully typed** - you get rich suggestions from your editor and the
  types can be fully checked.
* **Everything can be extended**.

.. toctree::
   :maxdepth: 2

   quick-start
   config
   topology
   classes
   runtime-requirements
   pytest
   api
