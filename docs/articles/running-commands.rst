Running Commands on Remote Hosts
################################

Running commands on remote hosts is one of the fundamental features of
pytest-mh. In order to do that, it provides abstraction over remote processes
and generic interface in the :class:`~pytest_mh.conn.Connection` class. There
are currently two implementations of this interface:

* SSH connection in :class:`~pytest_mh.conn.ssh.SSHClient` (using ``pylibssh``
  underneath)
* Direct communication with containers in
  :class:`~pytest_mh.conn.container.ContainerClient` (supports podman and
  docker)

This interface allows you to run commands and scripts in both blocking and
non-blocking manner. The main and generic connection to the host can be accessed
via :attr:`~pytest_mh.MultihostHost.conn` attribute of the
:class:`~pytest_mh.MultihostHost` class. If needed, you can establish additional
connections by instantiating one of the connection classes (for example to open
SSH connection to the host for different user).

.. note::

    Pytest-mh main connection expects that Linux commands are using ``bash`` and
    Windows commands are using ``powershell``.

    You can provide implementation for different shells by subclassing
    :attr:`~pytest_mh.conn.Shell` and passing this shell directly to the
    constructor of the connector. However, this should only be done for extra
    connections.

.. toctree::
    :maxdepth: 2

    running-commands/configuration
    running-commands/blocking-calls
    running-commands/non-blocking-calls
