Multihost Roles
###############

Objects that inherits from :class:`~pytest_mh.MultihostRole` are directly
accessible in the test. These objects are short-lived, new instance is created
for each test, therefore it is possible to store test related data. The main
purpose of this class is to provide role setup and teardown as well as a place
to implement high-level API for testing your project.

.. seealso::

    See :doc:`multihost-utilities` to see how is it possible to share code
    between multiple role classes (and host classes).

As a first example, we implement a basic code for a client role. This role
includes several built-in utilities to automatically get access to functionality
we want to use in our tests.

.. code-block:: python
    :caption: Example: Trivial client role
    :linenos:

    from pytest_mh import MultihostRole
    from pytest_mh.utils.firewall import Firewalld
    from pytest_mh.utils.fs import LinuxFileSystem
    from pytest_mh.utils.journald import JournaldUtils
    from pytest_mh.utils.services import SystemdServices
    from pytest_mh.utils.tc import LinuxTrafficControl

    class ClientRole(MultihostRole[ClientHost]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.fs: LinuxFileSystem = LinuxFileSystem(self.host)
            """
            File system manipulation.
            """

            self.svc: SystemdServices = SystemdServices(self.host)
            """
            Systemd service management.
            """

            self.firewall: Firewalld = Firewalld(self.host).postpone_setup()
            """
            Configure firewall using firewalld.
            """

            self.tc: LinuxTrafficControl = LinuxTrafficControl(self.host).postpone_setup()
            """
            Traffic control manipulation.
            """

            self.journald: JournaldUtils = JournaldUtils(self.host)
            """
            Journald utilities.
            """

        def setup(self) -> None:
            """
            Called before execution of each test.

            * stop the client
            * remove client's database and logs
            """
            super().setup()

            self.svc.stop("my-project-client")
            self.fs.rm("/var/lib/my-project-client")
            self.fs.rm("/var/log/my-project-client")

        def teardown(self) -> None:
            """
            Called after execution of each test.
            """
            # It is not required to restore removed files or restart
            # the service. This is done automatically by the utilities.
            super().teardown()

The following snippet add a high-level API to add a local user. It uses a
built-in CLI builder, that can help you to prepare a command line for execution.
Notice, that all local users that are created during a test are later removed
during teardown.

.. code-block:: python
    :caption: Example: Method to add a local user
    :emphasize-lines: 4,5,42-45,47-50,72-75,79-126
    :linenos:

    from typing import Self

    from pytest_mh import MultihostRole
    from pytest_mh.cli import CLIBuilder, CLIBuilderArgs
    from pytest_mh.conn import ProcessLogLevel
    from pytest_mh.utils.firewall import Firewalld
    from pytest_mh.utils.fs import LinuxFileSystem
    from pytest_mh.utils.journald import JournaldUtils
    from pytest_mh.utils.services import SystemdServices
    from pytest_mh.utils.tc import LinuxTrafficControl


    class ClientRole(MultihostRole[ClientHost]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.fs: LinuxFileSystem = LinuxFileSystem(self.host)
            """
            File system manipulation.
            """

            self.svc: SystemdServices = SystemdServices(self.host)
            """
            Systemd service management.
            """

            self.firewall: Firewalld = Firewalld(self.host).postpone_setup()
            """
            Configure firewall using firewalld.
            """

            self.tc: LinuxTrafficControl = LinuxTrafficControl(self.host).postpone_setup()
            """
            Traffic control manipulation.
            """

            self.journald: JournaldUtils = JournaldUtils(self.host)
            """
            Journald utilities.
            """

            self.cli: CLIBuilder = CLIBuilder(self.host.conn)
            """
            CLI builder helper.
            """

            self._added_users: list[str] = []
            """
            List of local users that were created during the test.
            """

        def setup(self) -> None:
            """
            Called before execution of each test.

            * stop the client
            * remove client's database and logs
            """
            super().setup()

            self.svc.stop("my-project-client")
            self.fs.rm("/var/lib/my-project-client")
            self.fs.rm("/var/log/my-project-client")

        def teardown(self) -> None:
            """
            Called after execution of each test.
            """
            # It is not required to restore removed files or restart
            # the service. This is done automatically by the utilities.

            # Delete users that we added
            if self._users:
                cmd = "\n".join([f"userdel '{x}' --force --remove" for x in self._users]) + "\n"
                self.host.conn.run("set -e\n\n" + cmd)

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
            self.host.conn.run(self.cli.command("useradd", args) + passwd, input=password, log_level=ProcessLogLevel.Error)

            self._users.append(name)

            return self

.. seealso::

    The examples above are very trivial in order to show the idea. To see a
    feature-rich roles that are actively used to test a real life project,
    checkout the `sssd-test-framework roles`_. These roles provide extensive,
    high-level API to manage users, group and other objects in LDAP, IPA,
    SambaDC and Active Directory as well as tools to manage and test SSSD.

.. _sssd-test-framework roles: https://github.com/SSSD/sssd-test-framework/tree/master/sssd_test_framework/roles

