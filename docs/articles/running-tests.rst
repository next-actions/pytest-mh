Running Tests
#############

Pytest-mh is a pytest plugin, therefore all tests are run with ``pytest``. There
are some additional command line arguments that you can use, all pytest-mh
arguments are prefixed with ``--mh-``. You can use the following command
to find all pytest-mh related parameters:

.. code-block:: text

    $ pytest --help | grep -C 5 -- --mh

The only required parameter is ``--mh-config`` that sets the path to the
pytest-mh configuration file.

.. grid:: 1

    .. grid-item-card::  Running pytest-mh tests

        .. tab-set::

            .. tab-item:: Command line

                .. code-block:: text

                    $ pytest --mh-config=mhc.yam --verbose

            .. tab-item:: Sample output

                .. code-block:: text

                    ...
                    tests/test_identity.py::test_identity__lookup_username_with_id[root] (ipa) PASSED                                                               [  2%]
                    tests/test_identity.py::test_identity__lookup_username_with_id[sssd] (ipa) SKIPPED (SSSD was built without support for running under non-root)  [  4%]
                    tests/test_identity.py::test_identity__lookup_uid_with_id[root] (ipa) PASSED                                                                    [  6%]
                    tests/test_identity.py::test_identity__lookup_uid_with_id[sssd] (ipa) SKIPPED (SSSD was built without support for running under non-root)       [  8%]
                    tests/test_identity.py::test_identity__lookup_groupname_with_getent (ipa) PASSED                                                                [ 10%]
                    tests/test_identity.py::test_identity__lookup_gid_with_getent (ipa) PASSED                                                                      [ 12%]
                    ...

Notice, that the test name in the output contains the multihost topology in
parentheses.

.. note::

    If a test requires a role, host or domain that is not included in the
    given configuration file, it is silently skipped.

Useful parameters
=================

This is a short list of selected pytest-mh parameters that can be useful when
running tests locally.

* ``--mh-topology``: Run only tests for selected topology
* ``--mh-not-topology``: Avoid running test for given topology
* ``--mh-artifacts-dir``: Store artifacts in non-default directory
* ``--mh-log-path=/dev/stderr``: Print pytest-mh log record to standard error output

.. seealso::

    You should definitely check out pytest documentation on how to run and
    filter tests: https://docs.pytest.org/en/latest/how-to/usage.html

Debugging tests
===============

Pytest-mh stores logs for each test run. These logs can be found among the test
artifacts in artifacts directory (by default ``./artifacts``). You can find them
in:

* ``./artifacts/tests/$test-case/test.log``: log records for the test run
* ``./artifacts/tests/$test-case/setup.log``: log records for the test setup phase
* ``./artifacts/tests/$test-case/teardown.log``: log records for the test teardown phase

.. note::

    By default, logs and artifacts are stored only for failed tests. You can
    modify this behavior with ``--mh-collect-artifacts`` and
    ``--mh-collect-logs``.

Lots of commands that are run have a log level set to ``Error`` therefore they
are added to the logs only if the command failed. This is usually the desired
behaviour so as not to clutter the logs with hundreds of successful commands.
However, sometimes it is useful to override this behavior and log everything.
You can do this by setting ``MH_CONNECTION_DEBUG=yes`` environment variable.

.. code-block:: text
    :caption: Log every remote command

    $ MH_CONNECTION_DEBUG=yes pytest --mh-config=mhc.yam --verbose
