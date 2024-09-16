Multihost Configuration
#######################

:class:`~pytest_mh.MultihostConfig` has access to the whole configuration file
that is used to run the tests. Its main purpose is to map domain identifier into
a Python class that will be used to create the domain object.

.. code-block:: python
    :caption: Basic example of MultihostConfig
    :emphasize-lines: 10-13
    :linenos:

    class MyProjectConfig(MultihostConfig):
        @property
        def id_to_domain_class(self) -> dict[str, Type[MultihostDomain]]:
            """
            Map domain id to domain class. Asterisk ``*`` can be used as fallback
            value.

            :rtype: Class name.
            """
            return {
                "example": MyProjectExampleDomain,
                "*": MyProjectGenericDomain
            }

However, it can also be used to add a custom top-level configuration options or
extend the functionality of ``pytest.mark.topology`` marker. The configuration
file contents can be accessed as a dictionary through
:attr:`~pytest_mh.MultihostConfig.confdict`, however it is recommended to place
custom options under the ``config`` field which can be accessed directly through
the :attr:`~pytest_mh.MultihostConfig.config` attribute. This way, it is
possible to avoid name collisions if pytest-mh introduces new options in the
future.

It is also possible to override or extend all public methods to further affect
the behavior.

.. grid:: 1

    .. grid-item-card:: Custom configuration option and topology marker

        .. tab-set::

            .. tab-item:: Python code

                .. code-block:: python
                    :emphasize-lines: 3-10,13-14,17-20
                    :linenos:

                    class MyProjectConfig(MultihostConfig):
                        @property
                        def required_fields(self) -> list[str]:
                            """
                            Fields that must be set in the host configuration. An error is raised
                            if any field is missing.

                            The field name may contain a ``.`` to check nested fields.
                            """
                            return super().required_fields + ["config.my_config_required_option"]

                        @property
                        def my_config_option(self) -> bool:
                            return self.config.get("my_config_option", False)

                        @property
                        def my_config_required_option(self) -> bool:
                            # This option is required and pytest will error if
                            # it is not present in the configuration
                            return self.config.get("my_config_required_option")

                        @property
                        def TopologyMarkClass(self) -> Type[TopologyMark]:
                            # Set a custom topology marker type
                            return MyProjectTopologyMark

                        @property
                        def id_to_domain_class(self) -> dict[str, Type[MultihostDomain]]:
                            """
                            Map domain id to domain class. Asterisk ``*`` can be used as fallback
                            value.

                            :rtype: Class name.
                            """
                            return {"*": SSSDMultihostDomain}


            .. tab-item:: mhc.yaml

                .. code-block:: yaml
                    :emphasize-lines: 1-3
                    :linenos:

                    config:
                        my_config_option: True
                        my_config_required_option: True
                    domains:
                    - id: example
                      hosts:
                      - hostname: client.test
                        role: client