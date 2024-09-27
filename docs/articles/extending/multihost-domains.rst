Multihost Domains
#################

:class:`~pytest_mh.MultihostDomain` has access to the domain part of the
configuration file. Its main purpose is to map role names into Python classes
that will be used to create the host and role objects.

.. code-block:: python
    :caption: Basic example of MultihostDomain
    :emphasize-lines: 12-15,27-30
    :linenos:

    class MyProjectDomain(MultihostDomain[MyProjectConfig]):
        @property
        def role_to_host_class(self) -> dict[str, Type[MultihostHost]]:
            """
            Map role to host class. Asterisk ``*`` can be used as fallback value.

            :rtype: Class name.
            """
            from .hosts.client import ClientHost
            from .hosts.server import ServerHost

            return {
                "client": ClientHost,
                "server": ServerHost,
            }

        @property
        def role_to_role_class(self) -> dict[str, Type[MultihostRole]]:
            """
            Map role to role class. Asterisk ``*`` can be used as fallback value.

            :rtype: Class name.
            """
            from .roles.client import ClientRole
            from .roles.server import ServerRole

            return {
                "client": ClientRole,
                "server": ServerRole,
            }

.. note::

    It may be required to import the types inside the methods to reduce their
    scope and avoid circular dependency since :class:`~pytest_mh.MultihostHost`
    is a generic class that takes the domain class as a specific type.

Similar to the :class:`~pytest_mh.MultihostConfig` class, it is also possible
to add custom configuration options or further extend functionality by
overriding the parent class methods. The configuration dictionary can be
accessed by :attr:`~pytest_mh.MultihostDomain.confdict`, however it is
recommended to place custom options under the ``config`` field which can be
accessed directly through the :attr:`~pytest_mh.MultihostDomain.config`
attribute. This way, it is possible to avoid name collisions if ``pytest-mh``
introduces new options in the future.

It is also possible to override or extend all public methods to further affect
the behavior.

.. grid:: 1

    .. grid-item-card:: Basic example of custom configuration option

        .. tab-set::

            .. tab-item:: Python code

                .. code-block:: python
                    :emphasize-lines: 3-10,13-14,17-20
                    :linenos:

                    class MyProjectDomain(MultihostDomain[MyProjectConfig]):
                        @property
                        def required_fields(self) -> list[str]:
                            """
                            Fields that must be set in the host configuration. An error is raised
                            if any field is missing.

                            The field name may contain a ``.`` to check nested fields.
                            """
                            return super().required_fields + ["config.my_domain_required_option"]

                        @property
                        def my_domain_option(self) -> bool:
                            return self.config.get("my_domain_option", False)

                        @property
                        def my_domain_required_option(self) -> bool:
                            # This option is required and pytest will error if
                            # it is not present in the configuration
                            return self.config.get("my_domain_required_option")

                        @property
                        def role_to_host_class(self) -> dict[str, Type[MultihostHost]]:
                            """
                            Map role to host class. Asterisk ``*`` can be used as fallback value.

                            :rtype: Class name.
                            """
                            from .hosts.client import ClientHost
                            from .hosts.server import ServerHost

                            return {
                                "client": ClientHost,
                                "server": ServerHost,
                            }

                        @property
                        def role_to_role_class(self) -> dict[str, Type[MultihostRole]]:
                            """
                            Map role to role class. Asterisk ``*`` can be used as fallback value.

                            :rtype: Class name.
                            """
                            from .roles.client import ClientRole
                            from .roles.server import ServerRole

                            return {
                                "client": ClientRole,
                                "server": ServerRole,
                            }


            .. tab-item:: mhc.yaml

                .. code-block:: yaml
                    :emphasize-lines: 3
                    :linenos:

                    domains:
                    - id: example
                      config:
                        my_domain_option: True
                        my_domain_required_option: True
                      hosts:
                      - hostname: client.test
                        role: client


