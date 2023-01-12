Multihost configuration
#######################

The multihost configuration file contains definition of the domains, hosts and
their roles that are available to run the tests. It uses the `YAML
<https://en.wikipedia.org/wiki/YAML>`__ language.

Basic definition
****************

.. code-block:: yaml

    domains:
    - type: <domain type>
      hosts:
      - hostname: <resolvable dns host name>
        role: <host role>
        username: <ssh username>
        password: <ssh password>
        config: <additional configuration> (optional)
        artifacts: <list of produced artifacts> (optional)

The top level element of the configuration is list of ``domains``. Each domain
has ``type`` attribute and defines the list of available hosts.

* ``type``: domain identifier which is used in the path inside ``mh`` fixture, see :ref:`mh-fixture`
* ``hosts``: list of available hosts and their roles

  * ``hostname``: DNS host name, must be resolvable
  * ``role``: host role
  * ``username``: ssh username, usually ``root``
  * ``password``: ssh password for the user
  * ``config``: additional configuration, place for custom options, see :ref:`custom-config`
  * ``artifacts``: list of artifacts that are automatically downloaded, see :ref:`gathering-artifacts`

.. code-block:: yaml
    :caption: Sample configuration file

    domains:
    - type: test
      hosts:
      - hostname: client.test
        role: client
        username: root
        password: Secret123
        artifacts:
        - /etc/sssd/*
        - /var/log/sssd/*
        - /var/lib/sss/db/*

      - hostname: master.ldap.test
        role: ldap
        username: root
        password: Secret123
        config:
          binddn: cn=Directory Manager
          bindpw: Secret123

.. _custom-config:

Customize configuration
=======================

The ``config`` section of the host configuration can be used to extend the
configuration with custom options that are required by your project. If the
field is not set, it defaults to an empty dictionary ``dict()``.

To make a new configuration option available, simply inherit from
:class:`~pytest_mh.MultihostHost` and access the option through
:attr:`~pytest_mh.MultihostHost.config` (``self.config``).

.. code-block:: python
  :caption: Adding custom configuration options

  class LDAPHost(MultihostHost[MyDomain]):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.binddn: str = self.config.get("binddn", "cn=Directory Manager")
        """Bind DN ``config.binddn``, defaults to ``cn=Directory Manager``"""

        self.bindpw: str = self.config.get("bindpw", "Secret123")
        """Bind password ``config.bindpw``, defaults to ``Secret123``"""

The example above adds two new options ``binddn`` and ``bindpw``. Since the
options provide default values, they are only optional. You can set them in
the multihost configuration in the ``config`` field.

.. code-block:: yaml

    domains:
    - type: test
      hosts:
      - hostname: client.test
        role: client
        username: root
        password: Secret123

      - hostname: master.ldap.test
        role: ldap
        username: root
        password: Secret123
        config:
          binddn: cn=Directory Manager
          bindpw: Secret123

.. _gathering-artifacts:

Gathering artifacts
===================

The ``artifacts`` field of the host definition can be used to specify which
artifacts should be automatically collected from the host when a test is
finished. The field contains a list of artifacts. The values are path to the
artifacts with a possible wildcard character. For example:

.. code-block:: yaml

  - hostname: client.test
    role: client
    username: root
    password: Secret123
    config:
      artifacts:
      - /etc/sssd/*
      - /var/log/sssd/*
      - /var/lib/sss/db/*
