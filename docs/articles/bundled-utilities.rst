Ready to Use Utilities
######################

Pytest-mh codebase contains several generic, ready to use utilities that you can
easily add to your hosts and roles. These utilities add support for various
project independent tasks, such as reading and writing files, managing firewall,
automatic collection of core dumps and much more.

In order to use these utilities, simply import them in your python module and
add them to your role or host.

.. warning::

    Only utilities that inherits from
    :class:`~pytest_mh.MultihostReentrantUtility` can be safely used in both
    :class:`~pytest_mh.MultihostRole` and :class:`~pytest_mh.MultihostHost`
    object. Other classes should be used only in
    :class:`~pytest_mh.MultihostRole`.

.. code-block:: python
    :caption: Example: Adding filesystem and systemd utilities to your role

    from pytest_mh import MultihostHost
    from pytest_mh.utils.fs import LinuxFileSystem
    from pytest_mh.utils.services import SystemdServices

    class ExampleRole(MultihostHost[ExampleDomain]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.fs: LinuxFileSystem = LinuxFileSystem(self)
            """
            File system utilities.
            """

            self.svc: SystemdServices = SystemdServices(self)
            """
            Systemd utilities.
            """

These utilities are automatically initialized, setup and teardown. You can start
using them right away. Every change on the host that these utilities do during
a test run is guarantied to be automatically reverted.

.. note::

    We welcome contributions that add more project independent utilities.

.. toctree::
    :maxdepth: 2

    bundled-utilities/auditd
    bundled-utilities/coredumpd
    bundled-utilities/firewall
    bundled-utilities/fs
    bundled-utilities/journald
    bundled-utilities/services
    bundled-utilities/tc
