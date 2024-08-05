Journald: Searching in the Journal
##################################

Systemd-journald is the daemon that collects system logs nowadays. This utility
dumps journal contents to a file and stores it as a test artifact. It also
exposes an API to run queries against the journal to search for messages that
were produced during the test run.

.. note::

    ``systemd-journald`` must be enabled on the system.

.. seealso::

    See the API reference of :class:`~pytest_mh.utils.journald.JournaldUtils`
    for more information.

Simply add this utility to your role in order to use it during a test run.
Everything else is fully automatic.

.. code-block:: python
    :caption: Example: Adding journald utility to your role

    from pytest_mh import MultihostHost
    from pytest_mh.utils.journald import JournaldUtils

    class ExampleRole(MultihostHost[ExampleDomain]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.journald: JournaldUtils = JournaldUtils(self.host)
            """
            Journald utilities.
            """

Adding this utility automatically produces ``/var/log/journald.log`` artifact
that contains dump of the journal log entries that were recorded during test.

.. code-block:: python
    :caption: Example: Check if a log message is present in the journal

    @pytest.mark.topology(...)
    def test_journal(client: ClientRole):
        ...
        assert client.journal.is_match("Offline", unit="my-unit")
        ...
