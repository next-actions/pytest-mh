Services: Starting and Stopping System Services
###############################################

:class:`~pytest_mh.utils.services.SystemdServices` provides interface to start,
stop, reload and manage systemd services. The state of the service is
automatically restored when a test is finished. For example if a service was
originally stopped and then started during a test, it is automatically stopped
when the test finishes.

.. note::

    ``systemd`` must be used to manage services on the system.

.. seealso::

    See the API reference of :class:`~pytest_mh.utils.services.SystemdServices`
    for more information.

.. code-block:: python
    :caption: Example: Adding systemd utility to your role

    from pytest_mh import MultihostHost
    from pytest_mh.utils.services import SystemdServices

    class ExampleRole(MultihostHost[ExampleDomain]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

        self.svc: SystemdServices = SystemdServices(self.host)
        """
        Systemd service management.
        """


.. code-block:: python
    :caption: Example: Starting a systemd service

    @pytest.mark.topology(...)
    def test_tc(client: ClientRole):
        ...
        client.svc.start("my-service.service")
        ...

.. note::

    This service is a subclass of :class:`~pytest_mh.MultihostReentrantUtility`,
    therefore you can safely use it also in :class:`~pytest_mh.MultihostHost`
    objects, not only in :class:`~pytest_mh.MultihostRole`.
