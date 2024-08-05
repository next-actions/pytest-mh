Firewall: Managing Network Access
#################################

The :mod:`pytest_mh.utils.firewall` provides generic interface to remote system
firewall as well as two specific implementations of this interface: Firewalld
and Windows Firewall.

These utilities allows you to create inbound and outbound rules to block or
allow access to specific ports, IP addresses or hostnames.

.. note::

    ``firewalld`` or the Windows Firewall must be enabled on the system.

.. seealso::

    See the API reference of :class:`~pytest_mh.utils.firewall.Firewall`,
    :class:`~pytest_mh.utils.firewall.Firewalld`,
    :class:`~pytest_mh.utils.firewall.WindowsFirewall` for more information.

.. note::

    Since the firewall also performs some setup actions, you probably want to
    mark the utility with :meth:`~pytest_mh.MultihostUtility.postpone_setup` so
    the setup method is called only if the firewall is actually used. This way,
    it saves some resources in tests that do not utilize the firewall.

.. code-block:: python
    :caption: Example: Adding firewall utility to your role

    from pytest_mh import MultihostHost
    from pytest_mh.utils.firewall import Firewall

    class ExampleRole(MultihostHost[ExampleDomain]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.firewall: Firewall = Firewalld(self.host).postpone_setup()
            """
            Configure firewall using firewalld.
            """

.. code-block:: python
    :caption: Example: Rejecting outgoing connections to host

    @pytest.mark.topology(...)
    def test_firewall(client: ClientRole, server: ServerRole):
        ...
        client.firewall.outbound.reject_host(server)
        ...

.. note::

    If you create a new firewall rule to block a connection, connections that
    are already established may not be terminated. Therefore if you start
    blocking a connection and application under test is already running,
    make sure that the application also drops active connections.
