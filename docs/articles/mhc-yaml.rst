Configuration File
##################

The configuration file (usually named ``mhc.yaml``) contains the definition of
which multihost domains and hosts are *at the moment* available to use for
testing. If all tests can be run with given set of hosts then all tests are
run, but it is perfectly possible to omit some host in order to run only a
subset of available tests -- the tests that require more or different hosts
are silently skipped.

The configuration file uses the YAML format.

.. code-block:: yaml

    config: <custom global configuration>
    domains:
    - id: <domain id>
      config: <custom domain configuration>
      hosts:
      - hostname: <dns hostname, should resolvable within the hosts>
        role: <host role>
        os:
          family: <host operating system family>
        conn:
          type: <connection type>
        config: <custom host configuration>
        artifacts:
        - <list of collected artifacts>

.. list-table:: Description of individual fields
    :header-rows: 1

    * - Field
      - Required
      - Default value
      - Description

    * - ``config``
      - No
      - ``dict()``
      - Custom global configuration

    * - ``domains``
      - **Yes**
      - *N/A*
      - List of multihost domains

    * - ``domains.id``
      - **Yes**
      - *N/A*
      - Domain identifier

    * - ``domains.config``
      - No
      - ``dict()``
      - Custom domain configuration

    * - ``domains.hosts``
      - **Yes**
      - *N/A*
      - List of domain's host

    * - ``hosts.hostname``
      - **Yes**
      - *N/A*
      - DNS hostname, should be resolvable within the hosts

    * - ``hosts.role``
      - **Yes**
      - *N/A*
      - Multihost role that this host fulfils

    * - ``hosts.os``
      - No
      - ``linux``
      - OS family: ``linux`` or ``windows``

    * - ``hosts.conn``
      - No
      - See :ref:`below <mhc-yaml-connection-type>`
      - How to connect to the host

    * - ``hosts.conn.type``
      - No
      - ``ssh``
      - | Connection type: ``ssh``, ``podman``, ``docker``
        | Additional properties are define by each type

    * - ``hosts.config``
      - No
      - ``dict()``
      - Custom host configuration

    * - ``hosts.artifacts``
      - No
      - ``list()``
      - List of artifacts to collect from the host

Minimal configuration
=====================

.. dropdown:: Minimal configuration example
    :color: primary
    :icon: code
    :open:

    .. tab-set::

        .. tab-item:: Minimal configuration

            .. code-block:: yaml

                domains:
                - id: example
                  hosts:
                  - hostname: hostname.example
                    role: client

        .. tab-item:: With expanded default values

            .. code-block:: yaml

                config:
                domains:
                - id: example
                  config:
                  hosts:
                  - hostname: hostname.example
                    role: client
                    os:
                      family: linux
                    conn:
                      type: ssh
                      host: $host.hostname
                      user: root
                      password: Secret123
                    config:
                    artifacts:

.. _mhc-yaml-connection-type:

Connection type
===============

The ``conn`` field declares how does pytest-mh connect to each hosts. Pytest-mh
has built-in connectors for ``ssh``, ``podman`` and ``docker``. Each connection
has additional properties. If the ``conn`` field is omitted, the default is
``type=ssh, user=root, password=Secret123, host=host.hostname``.

See more information about each connection type at
:doc:`running-commands/configuration`.
