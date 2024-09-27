Using Pytest Fixtures
#####################

At this moment, it is not possible to pass the ``pytest-mh`` roles that are
available to the test directly to `pytest fixtures <pytest_fixtures_>`_.
However, there is :func:`~pytest_mh.mh_fixture` decorator which is a wrapper
around ``@pytest.fixture`` that can be used instead.

.. code-block:: python
    :caption: Example use of @mh_fixture decorator

    @mh_fixture
    def my_fixture(client: Client, request: pytest.FixtureRequest):
        return client.role

    @mh_fixture
    def my_fixture_with_teardown(client: Client, request: pytest.FixtureRequest):
        yield client.role
        # teardown code

    @pytest.mark.topology(KnownTopology.LDAP)
    def test_example(client: Client, ldap: LDAP, my_fixture, my_fixture_with_teardown):
        pass

It can be used as any other pytest fixture, it is possible to pass other pytest
fixtures as an argument as well.

.. warning::

    At this moment, only the ``function`` fixture scope is supported.

.. _pytest_fixtures: https://docs.pytest.org/en/latest/explanation/fixtures.html
