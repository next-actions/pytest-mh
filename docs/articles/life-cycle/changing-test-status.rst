Changing Test Status
####################

Sometimes, it is required to run some additional checks when a test is finished
and maybe even change the test result from success to fail, or change the test
result category or how its result is displayed in the verbose output.

This is possible by invoking a pytest built-in hook
:func:`~_pytest.hookspec.pytest_report_teststatus`. This hook can be added to
:class:`~pytest_mh.MultihostUtility`, see:
:meth:`MultihostUtility.pytest_report_teststatus
<pytest_mh.MultihostUtility.pytest_report_teststatus>`

.. seealso::

    This feature is used in :class:`~pytest_mh.utils.auditd.Auditd` and
    :class:`~pytest_mh.utils.coredumpd.Coredumpd` in order to set the result
    category to a custom value and optionally also fail the test.

    If an AVC denial occurred during test, it is moved to ``AVC DENIALS``
    category. If a coredump occured, it is moved to ``COREDUMPS`` category.

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
