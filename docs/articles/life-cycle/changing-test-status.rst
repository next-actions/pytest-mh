Changing Test Status
####################

Sometimes, it is required to run some additional checks when a test is finished
and maybe even change the test result from success to fail, or change the test
result category or how its result is displayed in the verbose output.

This is possible by implementing :meth:`MultihostUtility.pytest_report_teststatus
<pytest_mh.MultihostUtility.pytest_report_teststatus>`, which is loosely based on
pytest's built-in hook :func:`~_pytest.hookspec.pytest_report_teststatus`. Unlike
the pytest hook, it returns a :class:`~pytest_mh.MHReportTestStatus` instance (or
``None``), which lets a utility both set the pytest status and request additional
pytest-mh-internal behavior, such as forcing artifact collection, independently of
one another.

.. seealso::

    This feature is used in :class:`~pytest_mh.utils.auditd.Auditd` and
    :class:`~pytest_mh.utils.coredumpd.Coredumpd` in order to set the result
    category to a custom value and optionally also fail the test.

    If an AVC denial occurred during test, it is moved to ``AVC DENIALS``
    category. If a coredump occured, it is moved to ``COREDUMPS`` category.

    Whenever ``pytest_report_teststatus`` returns
    ``MHReportTestStatus(force_artifacts_collection=True, ...)`` for a test (as
    above), artifacts for that test are collected regardless of the final test
    outcome, unless ``--mh-collect-artifacts=never`` is set. This means that, for
    example, a test that only produces a warning (and therefore still ``passed``)
    still has its artifacts collected even if ``--mh-collect-artifacts=on-failure``
    (the default) is used.

    .. dropdown:: Example source code
        :color: primary
        :icon: code

        .. tab-set::

            .. tab-item:: Auditd utility

                .. literalinclude:: ../../../pytest_mh/utils/auditd.py
                    :caption: Modifying the test result in Auditd
                    :pyobject: Auditd.pytest_report_teststatus

            .. tab-item:: Coredumpd utility

                .. literalinclude:: ../../../pytest_mh/utils/coredumpd.py
                    :caption: Modifying the test result in Coredumpd
                    :pyobject: Coredumpd.pytest_report_teststatus
