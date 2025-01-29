Multihost Utilities
###################

:class:`~pytest_mh.MultihostUtility` can be used to share code between different
:class:`~pytest_mh.MultihostRole` classes, in addition
:class:`~pytest_mh.MultihostReentrantUtility` can be used to share code between
roles but also between :class:`~pytest_mh.MultihostHost` classes.

.. seealso::

    Pytest-mh already provides several general-purpose utility classes that are
    ready to use in order to test your project. See :doc:`../bundled-utilities`
    for more information.

MultihostUtility
================

All instances of :class:`~pytest_mh.MultihostUtility` that are available within
:class:`~pytest_mh.MultihostRole` classes are automatically setup and teardown
before and after the test. This can be used to provide high-level API that also
cleans up after itself and to share this code between multiple roles.

.. code-block:: python
    :caption: Example utility to manage local users
    :linenos:

    from typing import Self

    from pytest_mh import MultihostHost, MultihostUtility
    from pytest_mh.cli import CLIBuilder, CLIBuilderArgs
    from pytest_mh.conn import ProcessLogLevel
    from pytest_mh.utils.fs import LinuxFileSystem


    class LocalUsersUtils(MultihostUtility[MultihostHost]):
        """
        Management of local users.

        .. note::

            All changes are automatically reverted when a test is finished.
        """

        def __init__(self, host: MultihostHost, fs: LinuxFileSystem) -> None:
            """
            :param host: Remote host instance.
            :type host: MultihostHost
            """
            super().__init__(host)

            self.cli: CLIBuilder = host.cli
            """
            CLI builder helper.
            """

            self.fs: LinuxFileSystem = fs
            """
            File system manipulation.
            """

            self._users: list[str] = []
            """
            List of local users that were created during the test.
            """

        def teardown(self) -> None:
            """
            Delete any added user and group.
            """
            cmd = ""

            if self._users:
                cmd = "\n".join([f"userdel '{x}' --force --remove" for x in self._users]) + "\n"
                self.conn.run("set -e\n\n" + cmd)

            super().teardown()

        def add_local_user(
            self,
            *,
            name: str,
            uid: int | None = None,
            gid: int | None = None,
            password: str | None = "Secret123",
            home: str | None = None,
            gecos: str | None = None,
            shell: str | None = None,
        ) -> Self:
            """
            Create new local user.

            :param uid: User id, defaults to None
            :type uid: int | None, optional
            :param gid: Primary group id, defaults to None
            :type gid: int | None, optional
            :param password: Password, defaults to 'Secret123'
            :type password: str, optional
            :param home: Home directory, defaults to None
            :type home: str | None, optional
            :param gecos: GECOS, defaults to None
            :type gecos: str | None, optional
            :param shell: Login shell, defaults to None
            :type shell: str | None, optional
            :return: Self.
            :rtype: Self
            """
            if home is not None:
                self.fs.backup(home)

            args: CLIBuilderArgs = {
                "name": (self.cli.option.POSITIONAL, name),
                "uid": (self.cli.option.VALUE, uid),
                "gid": (self.cli.option.VALUE, gid),
                "home": (self.cli.option.VALUE, home),
                "gecos": (self.cli.option.VALUE, gecos),
                "shell": (self.cli.option.VALUE, shell),
            }

            passwd = f" && passwd --stdin '{name}'" if password else ""
            self.logger.info(f'Creating local user "{name}" on {self.host.hostname}')
            self.conn.run(self.cli.command("useradd", args) + passwd, input=password, log_level=ProcessLogLevel.Error)

            self._users.append(name)

            return self

.. note::

    Before a test is run, the hosts are setup multiple times at different scopes
    and later teardown in the same order (see
    :doc:`../life-cycle/setup-and-teardown`). For this reason, it is not
    possible to use :class:`~pytest_mh.MultihostUtility` objects in
    :class:`~pytest_mh.MultihostHost` because it can not guarantee that its
    :meth:`~pytest_mh.MultihostUtility.setup` and
    :meth:`~pytest_mh.MultihostUtility.teardown` methods are called at proper
    places.

    In theory, it is possible, if you know what you are doing and call setup and
    teardown manually at desired place. However, it is not possible to call
    these methods multiple times, so you can only use it within a single setup
    scope (e.g. only in :meth:`MultihostHost.pytest_setup
    <pytest_mh.MultihostHost.pytest_setup>`). It is therefore highly
    recommended to use only :class:`~pytest_mh.MultihostReentrantUtility` in
    host objects.

MultihostReentrantUtility
=========================

:class:`~pytest_mh.MultihostReentrantUtility` objects are designed to work with
multiple setup scopes and therefore can be safely used inside
:class:`~pytest_mh.MultihostHost`. You can understand a setup scope as a pair of
setup and teardown hooks, every code that is executed between these calls is a
setup scope. ``pytest-mh`` currently defines the following scopes:

.. code-block:: text
    :caption: Setup scopes

      | MultihostHost.pytest_setup
      |      | TopologyController.topology_setup
    S |    T |      |
    E |    O |      |
    S |    P |    T | MultihostHost.setup
    S |    O |    E | TopologyController.setup
    I |    L |    S | TopologyController.teardown
    O |    O |    T | MultihostHost.teardown
    N |    G |      |
      |    Y |      |
      |      | TopologyController.topology_teardown
      | MultihostHost.pytest_teardown

All instances of :class:`~pytest_mh.MultihostReentrantUtility` are "entered"
(:meth:`MultihostReentrantUtility.__enter__
<pytest_mh.MultihostReentrantUtility.__enter__>`) when entering a new setup
scope and "exited" (:meth:`MultihostReentrantUtility.__exit__
<pytest_mh.MultihostReentrantUtility.__exit__>`) when the setup scope is leaved.
The implementation of the utility is expected to save its state in ``__enter__``
and restore to this state in ``__exit__`` -- revert all changes that where done
inside the setup scope when the scope is leaved.

A typical use case is to use the :class:`~pytest_mh.utils.fs.LinuxFileSystem`
utility to write or modify a configuration file. Since it is a reentrant
utility, it is possible to write a common configuration of your service in
:meth:`MultihostHost.pytest_setup <pytest_mh.MultihostHost.pytest_setup>`
(state=A) and then further modify it in :meth:`TopologyController.pytest_setup
<pytest_mh.TopologyController.topology_setup>` (state=B). The configuration is
in state B for all tests for given topology. Once all tests for this topology
are finished, the configuration is restored to state A and ready for next
topology to be run.

.. code-block:: text
    :caption: State changes

    MultihostHost.pytest_setup (None -> state A)

        TopologyController_1.topology_setup (state A -> state B)
              | test_for_topology_1__a
            B | test_for_topology_1__b
              | test_for_topology_1__c
        TopologyController_1.topology_teardown (state B -> state A)

        TopologyController_2.topology_setup (state A -> state C)
              | test_for_topology_2__a
            C | test_for_topology_2__b
              | test_for_topology_2__c
        TopologyController_2.topology_teardown (state C -> state A)

    MultihostHost.pytest_teardown (state A -> None)

The setup and teardown methods of :class:`~pytest_mh.MultihostReentrantUtility`
are still being called, although it is expected that they will not be used in
most implementations. They are, however, called only once: before
:meth:`MultihostHost.pytest_setup <pytest_mh.MultihostHost.pytest_setup>` and
after :meth:`MultihostHost.pytest_teardown
<pytest_mh.MultihostHost.pytest_teardown>`. The following snippet illustrates
when the methods are called:

.. code-block:: text
    :caption: Reentrant utilities callstack

    setup host utilities
    enter host utilities
    MultihostHost.pytest_setup

        enter host utilities
        TopologyController.topology_setup

            enter host utilities
            MultihostHost.setup
            TopologyController.setup

                test_a
                test_b
                ...

            TopologyController.teardown
            MultihostHost.teardown
            exit host utilities

        TopologyController.topology_teardown
        exit host utilities

    MultihostHost.pytest_teardown
    exit host utilities
    teardown host utilities

We can modify the ``LocalUsersUtils`` and convert it into a reentrant version so
we can safely add users even inside host and topology setup, see the following
example.

.. code-block:: python
    :caption: Reentrant version of user management
    :emphasize-lines: 10,36-39,46-56,58-66
    :linenos:

    from collections import deque
    from typing import Self

    from pytest_mh import MultihostHost, MultihostReentrantUtility
    from pytest_mh.cli import CLIBuilder, CLIBuilderArgs
    from pytest_mh.conn import ProcessLogLevel
    from pytest_mh.utils.fs import LinuxFileSystem


    class LocalUsersUtils(MultihostReentrantUtility[MultihostHost]):
        """
        Management of local users.

        .. note::

            All changes are automatically reverted when a test is finished.
        """

        def __init__(self, host: MultihostHost, fs: LinuxFileSystem) -> None:
            """
            :param host: Remote host instance.
            :type host: MultihostHost
            """
            super().__init__(host)

            self.cli: CLIBuilder = host.cli
            """
            CLI builder helper.
            """

            self.fs: LinuxFileSystem = fs
            """
            File system manipulation.
            """

            self._states: deque[list[str]] = deque()
            """
            Stored state for each setup scope.
            """

            self._users: list[str] = []
            """
            List of local users that were created during the test.
            """

        def __enter__(self) -> Self:
            """
            Save current state.

            :return: Self.
            :rtype: Self
            """
            self._states.append(self._users)
            self._users = []

            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            """
            Revert all changes done during current context.
            """
            if self._users:
                cmd = "\n".join([f"userdel '{x}' --force --remove" for x in self._users]) + "\n"
                self.conn.run("set -e\n\n" + cmd)

            self._users = self._states.pop()

        def add_local_user(
            self,
            *,
            name: str,
            uid: int | None = None,
            gid: int | None = None,
            password: str | None = "Secret123",
            home: str | None = None,
            gecos: str | None = None,
            shell: str | None = None,
        ) -> Self:
            """
            Create new local user.

            :param uid: User id, defaults to None
            :type uid: int | None, optional
            :param gid: Primary group id, defaults to None
            :type gid: int | None, optional
            :param password: Password, defaults to 'Secret123'
            :type password: str, optional
            :param home: Home directory, defaults to None
            :type home: str | None, optional
            :param gecos: GECOS, defaults to None
            :type gecos: str | None, optional
            :param shell: Login shell, defaults to None
            :type shell: str | None, optional
            :return: Self.
            :rtype: Self
            """
            if home is not None:
                self.fs.backup(home)

            args: CLIBuilderArgs = {
                "name": (self.cli.option.POSITIONAL, name),
                "uid": (self.cli.option.VALUE, uid),
                "gid": (self.cli.option.VALUE, gid),
                "home": (self.cli.option.VALUE, home),
                "gecos": (self.cli.option.VALUE, gecos),
                "shell": (self.cli.option.VALUE, shell),
            }

            passwd = f" && passwd --stdin '{name}'" if password else ""
            self.logger.info(f'Creating local user "{name}" on {self.host.hostname}')
            self.conn.run(self.cli.command("useradd", args) + passwd, input=password, log_level=ProcessLogLevel.Error)

            self._users.append(name)

            return self

Creating more setup-scopes in tests
-----------------------------------

The main purpose of :class:`~pytest_mh.MultihostUtility` is to share code
between roles; the main purpose of :class:`~pytest_mh.MultihostReentrantUtility`
is to share code between hosts. However, they are implemented using Python's
context management functions and therefore it is also possible to pass them into
the ``with`` statement. This can be used to create additional scopes within a
test, if needed.

The following example illustrates how you can change a file multiple times and
keep reverting it to its previous state every time the context manager is
destroyed.

.. code-block:: python
    :caption: Reentrant utility in tests
    :emphasize-lines: 3,5,7
    :linenos:

        @pytest.mark.topology(...)
        def test_ad_hoc_util(example: ExampleRole) -> None:
            with example.fs as fs_a:
                fs_a.write("/root/test", "content_a")

                with fs_a as fs_b:
                    fs_b.write("/root/test", "content_b")

                    with fs_b as fs_c:
                        fs_c.write("/root/test", "content_c")
                        assert fs_c.read("/root/test") == "content_c"

                    # content is restored to "content_b" here since fs_c.__exit__ was called

                    assert fs_b.read("/root/test") == "content_b"

                # content is restored to "content_a" here since fs_b.__exit__ was called

                assert fs_a.read("/root/test") == "content_a"

             # content is restored to original content (probably file was deleted) here since fs_a.__exit__ was called

Postponing utility setup
========================

Some utilities may require a complex setup method that consumes some time, but
at the same time these utilities can be used in your tests only sporadically,
therefore it does not make sense to run the setup for tests that do not actually
use it. For this purpose, it is possible to postpone setup of the utility to a
place when it is used for the first time.

It is possible to mark the utility with a decorator
:meth:`~pytest_mh.mh_utility_postpone_setup` or run
:meth:`MultihostUtility.postpone_setup
<pytest_mh.MultihostUtility.postpone_setup>` when it is instantiated. Either
way, the result is the same but calling the method gives you more control if you
want to see different behavior in different roles or hosts.

.. grid:: 1

    .. grid-item-card::  Examples of postpone utility

        .. tab-set::

            .. tab-item:: @mh_utility_postpone_setup decorator

                .. code-block:: python
                    :emphasize-lines: 3
                    :linenos:

                    from pytest_mh import mh_utility_postpone_setup

                    @mh_utility_postpone_setup
                    class ExampleUtility(MultihostUtility):
                        def setup(self):
                            pass

                        def teardown(self):
                            pass

            .. tab-item:: postpone_setup() method

                .. code-block:: python
                    :emphasize-lines: 5
                    :linenos:

                    class MyRole(MultihostRole):
                        def __init__(self, *args, **kwargs):
                            super().__init__(*args, **kwargs)

                            self.firewall: Firewalld = Firewalld(self.host).postpone_setup()

Creating ad-hoc utilities
=========================

Sometimes, the utility is used so rarely that it does not make sense to include
it in the role object at all. At such time, it is possible to create it directly
in the test. The setup and teardown, enter and exit methods are called
automatically.

.. code-block:: python
    :caption: Ad-hoc utility usage
    :emphasize-lines: 5
    :linenos:

        from pytest_mh.utils.fs import LinuxFileSystem

        @pytest.mark.topology(...)
        def test_ad_hoc_util(example: ExampleRole) -> None:
            with mh_utility(LinuxFileSystem(role.host)) as fs:
                fs.write("/root/test", "content")
                assert fs.read("/root/test") == "content"
