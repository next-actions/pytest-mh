Auditd: Testing for AVC denials
###############################

Auditd is a Linux audit daemon responsible for writing audit records to the
audit log file, usually ``/var/log/audit/audit.log``.

This utility adds this log file into the list of artifacts that are collected
after each test. It also detects AVC denials (usually caused by SELinux or
AppArmor). If an AVC denial is found, it can change the test status to
``failed`` and mark it as ``original-status/AVC DENIAL``.

.. note::

    ``Auditd`` and ``ausearch`` must be installed on the system for this utility
    to work.

.. seealso::

    See the API reference of :class:`~pytest_mh.utils.auditd.Auditd` for more
    information.

Simply add this utility to your role in order to use it during a test run.
Everything else is fully automatic.

.. code-block:: python
    :caption: Example: Adding auditd utility to your role

    from pytest_mh import MultihostHost
    from pytest_mh.utils.auditd import Auditd

    class ExampleRole(MultihostHost[ExampleDomain]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.auditd: Auditd = Auditd(self.host, avc_mode="fail", avc_filter="my_binary")
            """
            Auditd utilities.
            """

If the ``avc_mode`` is set to ``fail``, it will change the outcome of the test
to ``failed`` even if the test itself was successful. However, the original
outcome is still visible in the verbose output. You can also set it to ``warn``
to mark the test as ``AVC DENIAL``, but keep the test outcome intact; or to
``ignore`` to only collect the audit logs without affecting the test outcome or
category.

.. code-block:: text
    :caption: Example: Output of pytest run with AVC denial detected

    Selected tests will use the following hosts:
        audit: audit.test

    collected 545 items / 544 deselected / 1 selected

    tests/test_audit.py::test_audit (audit) PASSED/AVC DENIAL

    ======= 544 deselected, 1 AVC DENIALS in 0.94s =======

.. warning::

    It is not possible to run auditd inside a container therefore this utility
    can detect AVC denials only if the remote host is a virtual machine or bare
    metal.

    If you run your tests on containerized environment as well as on virtual
    machines, it is recommended to set ``avc_mode="ignore"`` for containers
    and ``avc_mode="fail"`` (or ``warn``) for runs on virtual machine.

