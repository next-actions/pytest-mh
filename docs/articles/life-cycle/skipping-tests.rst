Skipping Tests
##############

Pytest filtering options are used to run only the desired tests, but it may
be useful to skip a test based on some external condition: for example if
the product was built with a certain feature or not. If the feature is not
supported, tests that are using this feature must be skipped.

It is not possible to accomplish this with the built-in ``pytest.mark.skipif``
marker since it is evaluated too soon and only takes expressions, it does not
provide access to the fixtures. However, ``pytest-mh`` provides alternative
solutions.

.. seealso::

    Every project has its own specifics and it is not possible to implement
    generic feature detection and provide it out of the box. `ldap.features`
    property used in these examples is not part of pytest-mh. To see tips on how
    to implement feature detection for your project, see
    :doc:`../tips-and-tricks/features-detection`.

.. _mark.require:

Skipping individual tests
=========================

It is possible to skip individual tests with ``pytest.mark.require`` marker.
This marker takes a callable as parameter, if the callable evaluates to ``True``
the test is run. If it evaluates to ``False``, the test is skipped.

Parameters of the callable are all fixtures that are available to the test,
including all :class:`~pytest.MultihostRole` objects required by the test, that
is all dynamic fixtures defined by the topology.

.. warning::

    The skip condition is evaluated before :ref:`test setup <setup_test>` is
    performed to avoid complex setup and teardown for a test that is going to be
    skipped.

    Keep this in mind when accessing the role objects, since the role and its
    utilities setup method has not yet been called, therefore some properties
    may not be correctly initialized. It is up to you to make sure that you only
    access the properties that have been already set in your code.

    However, it is perfectly fine to run commands and access properties that do
    not depend on the setup.

.. grid:: 1

    .. grid-item-card::  Examples of pytest.mark.require

        .. tab-set::

            .. tab-item:: Pytest code

                .. code-block:: python
                    :emphasize-lines: 3-6,16-19,32
                    :linenos:

                    # Use a simple lambda function
                    @pytest.mark.topology(KnownTopology.LDAP)
                    @pytest.mark.require(
                        lambda ldap: "password_policy" in ldap.features,
                        "Server is not built with password policy support"
                    )
                    def test_skip__lambda(client: Client, ldap: LDAP):
                        pass


                    # Use a defined function
                    def require_password_policy(ldap: LDAP):
                        return "password_policy" in ldap.features

                    @pytest.mark.topology(KnownTopology.LDAP)
                    @pytest.mark.require(
                        require_password_policy,
                        "Server is not built with password policy support"
                    )
                    def test_skip__function(client: Client, ldap: LDAP):
                        pass


                    # Use a defined function that also returns a reason in a tuple
                    def require_password_policy(ldap: LDAP):
                        result = "password_policy" in ldap.features
                        reason = "Server is not built with password policy support"

                        return result, reason

                    @pytest.mark.topology(KnownTopology.LDAP)
                    @pytest.mark.require.with_args(require_password_policy)
                    def test_skip__function_and_reason(client: Client, ldap: LDAP):
                        pass

                .. note::

                    Notice the usage of ``with_args`` in the third example
                    ``test_skip__function_and_reason``. Pytest marker does not
                    allow single function as an argument and it must be worked
                    around by using ``with_args``.

                    See pytest documentation for more information:
                    :meth:`pytest.MarkDecorator.with_args`

            .. tab-item:: Pytest run result

                .. code-block:: text

                    tests/test_passkey.py::test_skip__lambda (ldap) SKIPPED (Server is not built with password policy support)
                    tests/test_passkey.py::test_skip__function (ldap) SKIPPED (Server is not built with password policy support)
                    tests/test_passkey.py::test_skip__function_and_reason (ldap) SKIPPED (Server is not built with password policy support)

Skipping topology
=================

Sometimes, it is not possible to run any tests from specific topology even
though all hosts and roles required by the topology are available -- for example
when your program was not built with functionality required to correctly setup
the topology. It is possible to achieve this by setting a skip condition by
overriding the :meth:`~pytest_mh.TopologyController.skip` method of
:class:`~pytest_mh.TopologyController`.

All dynamic fixtures defined by the topology are passed to the method, but this
time they are instances of :class:`~pytest_mh.MultihostHost` instead of
:class:`~pytest_mh.MultihostRole` since the role objects are only created for
tests and are not available at this point.

.. warning::

    The skip condition is evaluated before :ref:`topology setup
    <setup_topology>` is performed to avoid complex setup and teardown for
    tests that are going to be skipped.

    Keep this in mind when accessing the host objects, since the hosts and its
    utilities setup method has not yet been called, therefore some properties
    may not be correctly initialized. It is up to you to make sure that you only
    access the properties that have been already set in your code.

    However, it is perfectly fine to run commands and access properties that do
    not depend on the setup.

.. grid:: 1

    .. grid-item-card::  Examples of TopologyController.skip()

        .. tab-set::

            .. tab-item:: Pytest code

                .. code-block:: python

                    class PasswordPolicyTopology(TopologyController):
                        def skip(self, ldap: LDAPHost) -> str | None:
                            if "password_policy" not in ldap.features:
                                # Return reason to skip the tests
                                return "Server is not built with password policy support"

                            # Return None to run the tests
                            return None

            .. tab-item:: Pytest run result

                .. code-block:: text

                    tests/test_passkey.py::test_skip__lambda (ldap) SKIPPED (Server is not built with password policy support)
                    tests/test_passkey.py::test_skip__function (ldap) SKIPPED (Server is not built with password policy support)
                    tests/test_passkey.py::test_skip__function_and_reason (ldap) SKIPPED (Server is not built with password policy support)
