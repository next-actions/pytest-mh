Additional runtime requirements
###############################

Sometimes, topology itself is not enough to detect if the test can or can not
be run and you want to check for a runtime requirement like that your program
was built with certain configure flags or features.

This can be achieved with ``pytest.mark.require(condition[, reason])`` marker
that takes a function as a parameter and the test is skipped if the function
returns ``False`` (the requirement was not met).

The function takes all fixtures that are available to the test as parameters.

.. note::

    The function can either return ``bool`` or ``tuple[bool, str]``. In this
    case, the second value is the reason for skipping the test.

.. code-block:: python

    @pytest.mark.topology(KnownTopology.LDAP)
    @pytest.mark.require(
        lambda client: "files-provider" in client.features,
        "SSSD was not built with files provider"
    )
    def test_example_explicit_reason(client: Client, ldap: LDAP):
        pass

    @pytest.mark.topology(KnownTopology.LDAP)
    @pytest.mark.require(
        lambda client: ("files-provider" in client.features, "SSSD was not built with files provider")
    )
    def test_example_reason_as_tuple(client: Client, ldap: LDAP):
        pass

    @pytest.mark.topology(KnownTopology.LDAP)
    @pytest.mark.require(
        lambda **kwargs: "files-provider" in kwargs["client"].features
    )
    def test_example_kwargs(client: Client, ldap: LDAP):
        pass

It is also possible to pass a function directly instead of an anonymous (lambda)
function if the requirement is shared between multiple tests. However, there is
a documented glitch in pytest that requires you to use different marker syntax.
See `pytest documentation
<https://docs.pytest.org/en/stable/example/markers.html#passing-a-callable-to-custom-markers>`__
for more information.

.. code-block:: python

    def require_files_provider(client: Client):
        return "files-provider" in client.features, "SSSD was not built with files provider"

    @pytest.mark.require.with_args(require_files_provider)
    @pytest.mark.topology(KnownTopology.LDAP)
    def test_example():
        pass

.. note::

    The requirement is evaluated when the test is executed but before setup
    phase, so no setup method was called on any multihost role in order to make
    the skip fast.

    If you require to setup the role, you can always call the setup method
    directly from the function passed to the ``require`` marker.

.. warning::

    ``pytest-mh`` provides the ``requirement`` marker as a generic way to skip
    a test when a condition is not met. The condition can use multihost roles
    or other pytest fixtures used by the marked test and it can also call
    commands on remote hosts.

    The example above shows a check if an SSSD project was built with
    "files-provider" feature, however feature detection is not part of
    ``pytest-mh`` since feature detection is project specific mechanism.
