Traffic Control: Delaying Network Traffic
#########################################

``tc`` is a tool to manipulate network traffic control setting. This utility
allows you to delay communication with target host which can simulate high
network latencies or delays.

.. note::

    ``tc`` tool must be installed on the system.

.. seealso::

    See the API reference of :class:`~pytest_mh.utils.tc.LinuxTrafficControl`
    for more information.

.. note::

    Since the utility also performs some setup actions, you probably want to
    mark the utility with :meth:`~pytest_mh.MultihostUtility.postpone_setup` so
    the setup method is called only if the tc tool is actually used. This way,
    it saves some resources in tests that do not utilize the traffic control.

.. code-block:: python
    :caption: Example: Adding tc utility to your role

    from pytest_mh import MultihostHost
    from pytest_mh.utils.tc import LinuxTrafficControl

    class ExampleRole(MultihostHost[ExampleDomain]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.tc: LinuxTrafficControl = LinuxTrafficControl(self.host).postpone_setup()
            """
            Traffic control manipulation.
            """


.. code-block:: python
    :caption: Example: Delaying traffic to host

    @pytest.mark.topology(...)
    def test_tc(client: ClientRole, server: ServerRole):
        ...
        # Delay traffic between client and server by 1500ms
        client.tc.add_delay(server, 1500)
        ...
