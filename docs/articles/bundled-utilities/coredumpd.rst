Coredumpd: Autodetection of Core Files
######################################

Detects core dumps produced during a test run using ``coredumpctl`` and stores a
backtrace together with a compressed core file as test artifacts. If any core
dump was produced during the test run, it can change the test status to
``failed`` and mark it as ``original-status/COREDUMP``.

.. note::

    ``systemd-coredump`` must be enabled on the system. Any ``Storage`` mode is
    supported since the core dumps are queried through ``coredumpctl``.

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

            self.coredumpd: Coredumpd = Coredumpd(
                self.host,
                self.fs,
                mode="fail",
                filter={
                    "fail": ["sssd*", "/usr/sbin/sssd"],
                    "ignore": ["unrelated_binary", "re:/usr/lib/.*"],
                },
            )
            """
            Coredumpd utilities.
            """

The ``filter`` classifies core dumps by their executable path. A core dump that
matches the ``fail`` filter always fails the test and one that matches the
``ignore`` filter is always ignored (it is still collected as an artifact). Each
filter takes a list of patterns; a pattern is a bare binary name matched against
the base name (a shell-style glob, e.g. ``sssd_be`` or ``sssd*``), a full path
matched against the executable path (a shell-style glob, e.g. ``/usr/sbin/sssd``
or ``/usr/libexec/sssd/*``) or a regular expression prefixed with ``re:`` (e.g.
``re:/usr/lib/.*``). A plain string without wildcards matches exactly.

A core dump that matches neither filter (an unexpected core dump in a random
binary) is handled according to ``mode``: it fails the test if ``mode="fail"``,
only marks it as ``COREDUMP`` while keeping the outcome intact if ``mode="warn"``
or is ignored if ``mode="ignore"`` (the default). The original test outcome is
always visible in the verbose output.

.. code-block:: text
    :caption: Example: Output of pytest run with core file detected

    Selected tests will use the following hosts:
        coredumpd: coredumpd.test

    collected 545 items / 544 deselected / 1 selected

    tests/test_coredumpd.py::test_coredumpd (coredumpd) PASSED/COREDUMP

    ======= 544 deselected, 1 COREDUMPS in 0.94s =======
