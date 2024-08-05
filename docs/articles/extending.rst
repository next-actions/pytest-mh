Extending pytest-mh for Your Needs
##################################

Pytest-mh uses a yaml-formatted configuration file that contains the list of
multihost domains, hosts and their roles that are required for the tests. These
configuration entities are converted into their Python representations that can
and should be extended to provide additional configuration and high level API
for your project as well as the setup and teardown code.

.. note::

    Do not confuse ``domains`` with DNS domains. The domains in the
    configuration file do not have to follow any DNS patterns. Their purpose is
    to identify a group of hosts.

    As a general rule, hosts within the same domain that have the same role
    should be interchangeable -- it should not matter to which of the host you
    talk, you always should get the same result, for example a database replicas
    or servers behind a load balancer.

The following snippet shows a minimal configuration file with one domain and one
host.

.. code-block:: yaml
    :caption: Minimal configuration file

    domains:
    - id: example
      hosts:
      - hostname: client.test
        role: client

The file is parsed into:

* :class:`~pytest_mh.MultihostConfig`: top level object, container for the whole
  configuration
* :class:`~pytest_mh.MultihostDomain`: the domain object, container for all
  hosts within a domain, one for each domain
* :class:`~pytest_mh.MultihostHost`: individual hosts, one for each host

Additionally, each host has a role assigned. This role creates a
:class:`~pytest_mh.MultihostRole` object, this object has a short lifespan and
it exists only for a duration of one test. A new role object is created for each
test. Further, :class:`~pytest_mh.MultihostUtility` classes can be used to share
code and functionality between roles and hosts.

Each test is assigned with a topology. A topology describes what domains and
roles are required to run the test. If the current configuration does not satisfy
this requirement, the test is silently skipped.

Read the following articles to get more information on how to define topologies
and use and extend these classes.

.. toctree::
    :maxdepth: 2

    extending/multihost-config
    extending/multihost-domains
    extending/multihost-hosts
    extending/multihost-roles
    extending/multihost-utilities
    extending/multihost-topologies
