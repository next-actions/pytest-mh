Host Backup and Restore
#######################

Various :doc:`setup and teardown <../life-cycle/setup-and-teardown>` hooks
called by ``pytest-mh`` can be used to implement automatic host backup and restore
functionality. This is supported out of the box with
:class:`~pytest_mh.MultihostBackupHost` and
:class:`~pytest_mh.BackupTopologyController`.

Implementing automatic backup of a host
=======================================

:class:`~pytest_mh.MultihostBackupHost` is an abstract class that declares
several abstract methods that have to be implemented:

.. container:: wy-table-responsive

    .. list-table::
        :widths: 30 70
        :header-rows: 1

        * - Abstract method name
          - Description
        * - :meth:`~pytest_mh.MultihostBackupHost.start`
          - Start required host services. If no services are needed, this can be
            implemented as a "no operation" or raise ``NotImplementedError``
            which will be ignored by internal calls to this method.
        * - :meth:`~pytest_mh.MultihostBackupHost.stop`
          - Stop required host services. If no services are needed, this can be
            implemented as a "no operation" or raise ``NotImplementedError``
            which will be ignored by internal calls to this method.
        * - :meth:`~pytest_mh.MultihostBackupHost.backup`
          - Take backup of the host. The backup can be returned as any Python
            data, :class:`~pathlib.PurePath` or a sequence of
            :class:`~pathlib.PurePath`. If the path is returned, it is
            automatically deleted from the host when all tests are run. If
            non-path data is returned, any clean up is left on the user if
            needed -- it is possible to override
            :meth:`~pytest_mh.MultihostBackupHost.remove_backup`.
        * - :meth:`~pytest_mh.MultihostBackupHost.restore`
          - Restore the host from the backup.

The backup is taken automatically during pytest setup, the host is restored
to this state after each test run. Sometimes, it is not desirable to restore the
host automatically at this point (for example if this is done by the topology
controller) and this can be disabled by passing ``auto_restore=False`` to the
constructor.

.. code-block:: python
    :caption: Example use of MultihostBackupHost

    class ExampleBackupHost(MultihostBackupHost[MyProjectMultihostDomain]):
        def __init__(self, *args, **kwargs) -> None:
            # restore is handled in topology controllers
            super().__init__(*args, auto_restore=False, **kwargs)

            self.svc: SystemdServices = SystemdServices(self)

    def start(self) -> None:
        self.svc.start("my-project")

    def stop(self) -> None:
        self.svc.stop("my-project")

    def backup(self) -> Any:
        self.logger.info("Creating backup of my-project service")

        # yields backup path
        result = self.conn.run("my-project create-backup", log_level=ProcessLogLevel.Error)

        return PurePosixPath(result.stdout_lines[-1].strip())

    def restore(self, backup_data: Any | None) -> None:
        if backup_data is None:
            return

        if not isinstance(backup_data, PurePosixPath):
            raise TypeError(f"Expected PurePosixPath, got {type(backup_data)}")

        backup_path = str(backup_data)
        self.logger.info(f"Restoring my-project from {backup_path}")
        self.stop()
        self.conn.run(f"my-project restore {backup_path}", log_level=ProcessLogLevel.Error)
        self.start()

.. note::

    Some projects can not take online backups and the services must be stopped.
    In such case, it is possible to pass ``auto_start=False`` to the constructor
    to prevent automatic start up of the service before taking the first backup.

    In this case, you must start the service manually when it is desired, for
    example after the backup is taken or in
    :meth:`~pytest_mh.MultihostBackupHost.setup`.

    .. code-block:: python
        :caption: Example use of MultihostBackupHost with no auto start
        :emphasize-lines: 3,12,15
        :linenos:

        class ExampleBackupHost(MultihostBackupHost[MyProjectMultihostDomain]):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, auto_start=False, **kwargs)

                self.svc: SystemdServices = SystemdServices(self)

        ...

        def backup(self) -> Any:
            self.logger.info("Creating backup of my-project service")

            self.stop()
            # yields backup path
            result = self.conn.run("my-project create-backup", log_level=ProcessLogLevel.Error)
            self.start()

            return PurePosixPath(result.stdout_lines[-1].strip())

        ...

.. warning::

    Using reentrant utilities (instances of
    :class:`~pytest_mh.MultihostReentrantUtility`) inside
    :meth:`~pytest_mh.MultihostBackupHost.backup` and
    :meth:`~pytest_mh.MultihostBackupHost.restore` may not work as you might
    expect. Remember that the reentrant utilities revert their actions during
    teardown of the scope where they exist. However, backup and restore are
    called from different scopes: :meth:`~pytest_mh.MultihostBackupHost.backup`
    is called from :meth:`~pytest_mh.MultihostBackupHost.pytest_setup`
    (per-session scope), but :meth:`~pytest_mh.MultihostBackupHost.restore` is
    called from :meth:`~pytest_mh.MultihostBackupHost.teardown` (per-test
    scope). It is therefore better to avoid them, unless you are sure that it
    does what you want.

    It is safer to use the :class:`~pytest_mh.utils.services.SystemdServices`
    in the examples above, because the expected service state is ``started``
    after both backup and restore.


Implementing automatic backup for a topology
============================================

The previous section showed how to implement an automatic backup for each host.
However, it is quite often the case that each host needs to get additional setup
in order to prepare it for a given topology (like configuring the particular
database backend that we want to test with this topology).

The topology controller provides various setup and teardown hooks that can setup
the topology, take backup, restore to this backup after each test and when all
tests for this topology are run, it can restore the hosts to their original
state before the topology setup was run.

This behavior is implemented by the built-in
:class:`~pytest_mh.BackupTopologyController`. This controller can be used as is
or further modified. Usually, it is desirable to override
:meth:`~pytest_mh.BackupTopologyController.topology_setup` to prepare the hosts
for testing. The automatic backup and restore is implemented only for the hosts
that inherits from :class:`~pytest_mh.MultihostBackupHost`.

.. warning::

    if :class:`~pytest_mh.BackupTopologyController` is used, make sure to
    disable automatic teardown in the hosts by passing ``auto_restore=False`` to
    the :class:`~pytest_mh.MultihostBackupHost` constructor.

.. code-block:: python
    :caption: Example use of BackupTopologyController

    class MyProjectTopologyController(BackupTopologyController[MyProjectMultihostConfig]):
        @BackupTopologyController.restore_vanilla_on_error
        def topology_setup(self, client: ClientHost, server: ServerHost) -> None:
            self.logger.info(f"Preparing {server.hostname}")

            # run your code

            # Backup so we can restore to this state after each test
            # There is no need to pass any arguments to this call
            super().topology_setup()

.. note::

    ``@BackupTopologyController.restore_vanilla_on_error`` decorator is used to
    restore the hosts to the original state before topology setup was called if
    any error occurs during the setup.
