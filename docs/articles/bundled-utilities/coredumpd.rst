Coredumpd: Autodetection of Core Files
######################################

Collects generated core files from ``/var/lib/systemd/coredump`` and stores them
as test artifacts. If any core file was produced during the test run, it can
change the test status to ``failed`` and mark it as
``original-status/COREDUMP``.

.. note::

    ``systemd-coredump`` must be enabled on the system and set to store core
    files in ``/var/lib/systemd/coredump`` directory (default behavior).

.. seealso::

    See the API reference of :class:`~pytest_mh.utils.coredumpd.Coredumpd` for
    more information.

Simply add this utility to your role in order to use it during a test run.
Everything else is fully automatic.

.. code-block:: python
    :caption: Example: Adding coredumpd utility to your role

    from pytest_mh import MultihostHost
    from pytest_mh.utils.fs import LinuxFileSystem
    from pytest_mh.utils.coredumpd import Coredumpd

    class ExampleRole(MultihostHost[ExampleDomain]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.fs: LinuxFileSystem = LinuxFileSystem(self.host)
            """
            File system manipulation.
            """

            self.coredumpd: Coredumpd = Coredumpd(self.host, self.fs, mode="fail", filter="my_binary")
            """
            Coredumpd utilities.
            """

If the ``mode`` is set to ``fail``, it will change the outcome of the test to
``failed`` even if the test itself was successful. However, the original outcome
is still visible in the verbose output. You can also set it to ``warn`` to mark
the test as ``COREDUMP`` but keep the test outcome intact; or to ``ignore`` to
only collect the core files but do not affect the test outcome or category.

.. code-block:: text
    :caption: Example: Output of pytest run with core file detected

    Selected tests will use the following hosts:
        coredumpd: coredumpd.test

    collected 545 items / 544 deselected / 1 selected

    tests/test_coredumpd.py::test_coredumpd (coredumpd) PASSED/COREDUMP

    ======= 544 deselected, 1 COREDUMPS in 0.94s =======
