Configuring the Main Connection
###############################

The main connection can be configured in the ``conn`` field of the host
configuration in pytest-mh configuration file (``mhc.yaml``).

.. code-block:: yaml

    hosts:
    # Configuring SSH connection, using a password
    - hostname: client1.test
      role: client
      conn:
        type: ssh
        host: 192.168.0.10 # IP address or hostname
        user: root
        password: Secret123

    # Configuring SSH connection, using a certificate
    - hostname: client2.test
      role: client
      conn:
        type: ssh
        host: 192.168.0.20 # IP address or hostname
        user: root
        private_key: /my/private/key/path
        private_key_password: Secret12

    # Configuring podman connection
    - hostname: client3.test
      role: client
      conn:
        type: podman
        container: client3

    # Configuring podman connection to a container running under root
    - hostname: client4.test
      role: client
      conn:
        type: podman
        container: client4
        sudo: True
        sudo_password: MyPassword # Can be omitted with password-less sudo

    # Default is SSH connection with host=hostname, user=root, password=Secret123
    - hostname: client5.test
      role: client
