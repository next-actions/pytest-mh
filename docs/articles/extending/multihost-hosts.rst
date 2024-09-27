Multihost Hosts
###############

:class:`~pytest_mh.MultihostHost` has access to the host part of the
configuration file. Its main purpose is to setup and teardown the host,
preparing it to run tests. It also provides the main connection to the host
making it possible to run remote commands (see
:attr:`~pytest_mh.MultihostHost.conn` attribute).

The host objects are created once when pytest starts and live for the whole
duration of the pytest session. Therefore they can be used to store data that
should be available to all tests.

.. note::

    The host class can be also used to provide high-level API for your project,
    however remember that the test has direct access to the
    :class:`MultihostRole` objects and only indirect access to the host objects
    (via the role). Therefore the vast majority of your high-level API should be
    placed in the role object in order to provide most direct access.

.. code-block:: python
    :caption: Basic example of MultihostHost
    :emphasize-lines: 8,18,26,36
    :linenos:

    class ClientHost(MultihostHost[MyProjectDomain]):
        def pytest_setup(self) -> None:
            """
            Called once before execution of any tests.
            """
            # Run your setup code here.
            # Do not forget to call the parent setup as well.
            super().pytest_setup()
            self.conn.run("echo 'Setting up'")

        def pytest_teardown(self) -> None:
            """
            Called once after all tests are finished.
            """
            # Run your teardown code here.
            # Do not forget to call the parent teardown as well.
            self.conn.run("echo 'Tearing down'")
            super().pytest_teardown()

        def setup(self) -> None:
            """
            Called before execution of each test.
            """
            # Run your setup code here.
            # Do not forget to call the parent setup as well.
            super().setup()
            self.conn.run("echo 'Setting up'")

        def teardown(self) -> None:
            """
            Called after execution of each test.
            """
            # Run your teardown code here.
            # Do not forget to call the parent teardown as well.
            self.conn.run("echo 'Tearing down'")
            super().teardown()

.. seealso::

    There are several methods where you can place your setup and teardown code.
    See :doc:`../life-cycle/setup-and-teardown`.

.. seealso::

    The host class is a perfect place to implement host-level backup and
    teardown. See :doc:`../tips-and-tricks/backup-restore` for tips on how to
    achieve that with :class:`~pytest_mh.MultihostBackupHost`.

It is also possible to add custom configuration options or further extend
functionality by overriding the parent class methods. The configuration
dictionary can be accessed by :attr:`~pytest_mh.MultihostHost.confdict`, however
it is recommended to place custom options under the ``config`` field which can
by accessed through the :attr:`~pytest_mh.MultihostHost.config` attribute. This
way, it is possible to avoid collisions if pytest-mh introduces new options in
the future.

.. grid:: 1

    .. grid-item-card:: Basic example of custom configuration option

        .. tab-set::

            .. tab-item:: Python code

                .. code-block:: python
                    :emphasize-lines: 3-10,13-14,17-20
                    :linenos:

                    class ClientHost(MultihostHost[MyProjectDomain]):
                        @property
                        def required_fields(self) -> list[str]:
                            """
                            Fields that must be set in the host configuration. An error is raised
                            if any field is missing.

                            The field name may contain a ``.`` to check nested fields.
                            """
                            return super().required_fields + ["config.my_host_required_option"]

                        @property
                        def my_host_option(self) -> bool:
                            return self.config.get("my_host_option", False)

                        @property
                        def my_host_required_option(self) -> bool:
                            # This option is required and pytest will error if
                            # it is not present in the configuration
                            return self.config.get("my_host_required_option")

            .. tab-item:: mhc.yaml

                .. code-block:: yaml
                    :emphasize-lines: 3
                    :linenos:

                    domains:
                    - id: example
                      hosts:
                      - hostname: client.test
                        role: client
                        config:
                          my_host_option: True
                          my_host_required_option: True
