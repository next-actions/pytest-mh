Features Detection
##################

Many projects can be built and distributed differently on different systems,
some features may be disabled or use different (usually hard-coded) settings.
This is quite common for compiled programs, that may choose to built or omit
some parts of the code.

Pytest-mh does not provide any built-in support of feature detection as this
functionality is highly project specific, but it is possible to use the
following code snippets as a guideline or inspiration.

Add feature property to the host class
======================================

Most of the time, it is desirable to detect the features only on start up, since
the application does not change the built-time features during testing.
Therefore, the code can be safely added to the host class and use
:meth:`~pytest_mh.MultihostHost.pytest_setup` to make sure it is run only once.

.. code-block:: python
    :caption: Creating base host class with feature property
    :emphasize-lines: 5,11-19
    :linenos:

    class BaseFeatureDetectionHost(MultihostHost[MyProjectDomain]):
        def __init__(*args, **kwargs):
            super().__init__(*args, **kwargs)

            self.features: dict[str, bool] = {}
            """
            Features supported by the host.
            """

    class MyProjectHost(BaseFeatureDetectionHost):
        def pytest_setup(self) -> None:
            super().pytest_setup()

            # the following is a pseudocode which yields list of available
            # features to stdout
            result = self.conn.run("detect-project-features")

            for feature_name in result.stdout_lines:
                self.features[name] = True

Add feature property to the role class
======================================

Since tests have only indirect access to the host object via roles, it may be
nice to provide a shortcut to make the code smaller. It would be possible to
assign ``self.features = self.host.features`` directly in the constructor,
however it might be better to use the ``@property`` decorator to also cover the
case when ``host.features`` changes reference to different dictionary/object.

.. code-block:: python
    :caption: Add shortcut to the host feature to the role class
    :emphasize-lines: 2-7
    :linenos:

    class MyProjectRole(MyProjectHost):
        @property
        def features(self) -> dict[str, bool]:
            """
            Features supported by the role.
            """
            return self.host.features

Skipping tests
==============

It is possible to check for a feature presence using :ref:`@pytest.mark.require
<mark.require>`, if the feature is not available the test will be skipped.

.. code-block:: python
    :emphasize-lines: 2-5
    :linenos:

    @pytest.mark.topology(KnownTopology.LDAP)
    @pytest.mark.require(
        lambda ldap: "password_policy" in ldap.features,
        "Server is not built with password policy support"
    )
    def test_skip__lambda(client: Client, ldap: LDAP):
        pass

.. seealso::

    You can also inspire in the SSSD project that has a syntactic sugar over the
    ``@pytest.mark.require`` marker and introduces ``@pytest.mark.builtwith``,
    which internally translates into the ``require`` marker. You can check out
    the code `here
    <https://github.com/SSSD/sssd-test-framework/blob/0b213ff8fca10a5de55f34f7f2bc94cdba4a3487/sssd_test_framework/markers.py#L28-L54>`__
    and `here
    <https://github.com/SSSD/sssd-test-framework/blob/0b213ff8fca10a5de55f34f7f2bc94cdba4a3487/sssd_test_framework/markers.py#L64-L101>`__.

    .. code-block:: python
        :caption: Example use of SSSD's builtwith marker
        :emphasize-lines: 2,8
        :linenos:

        # require files-provider feature built in the client
        @pytest.mark.builtwith("files-provider")
        @pytest.mark.topology(KnownTopology.Client)
        def test_files__root_user_is_ignored_on_lookups(client: Client):
            ...

        # require passkey feature built in the client and the provider
        @pytest.mark.builtwith(client="passkey", provider="passkey")
        @pytest.mark.topology(KnownTopologyGroup.AnyProvider)
        def test_passkey__su_user(client: Client, provider: GenericProvider, moduledatadir: str, testdatadir: str):
            ...
