Using pytest-mh
###############

Register plugin with pytest
***************************

``pytest-mh`` plugin does not autoregister itself with pytest, it rather lets
you do it manually in ``conftest.py``. It also requires you to set your own
:class:`~pytest_mh.MultihostConfig` class so the plugin knows what domain, host
and role objects should be created.

.. code-block:: python
    :caption: Registering pytest-mh with pytest in conftest.py

    from pytest_mh import MultihostPlugin

    # Load additional plugins
    pytest_plugins = (
        "pytest_mh",
    )


    # Setup pytest-mh and tell it to use "ExampleMultihostConfig" class
    def pytest_plugin_registered(plugin) -> None:
        if isinstance(plugin, MultihostPlugin):
            plugin.config_class = ExampleMultihostConfig

.. seealso::

    Read :doc:`classes` and :doc:`quick-start` to see how to implement your own
    configuration, domain, hosts and roles classes by extending base classes
    provided by :mod:`pytest_mh`.

Running tests
*************

In order to run the tests, you need to provide multihost configuration (see
:doc:`config` for more details). Once you have it, you can run your test suite
with pytest as usually, you just need to specify path to the configuration with
``--mh-config=<path-to-mhc.yaml>``.

.. code-block:: console

    $ pytest --mh-config=./mhc.yaml

New pytest command line options
===============================

``pytest-mh`` adds several command line options to the pytest.

* ``--mh-config=<path>`` - Path to the multihost configuration file in YAML
  format.
* ``--mh-log-path`` - Path to the log file where multihost messages will be
  written.
* ``--mh-lazy-ssh`` - If set, SSH connection to the host not established
  immediately but it is postponed to its first use. Otherwise the connection to
  all hosts is established immediately when pytest starts to test if all hosts
  are accessible.
* ``--mh-exact-topology`` - If set, test is run only if its topology matches
  exactly given multihost configuration. Otherwise it is sufficient that the
  topology can be fulfilled by the configuration even though the configuration
  may contain more hosts or domains then are required.
* ``--mh-collect-artifacts=always|on-failure|never`` - Specifies when test
  artifacts are collected. Default value is ``on-failure`` - only collect
  artifacts if test fails.
* ``--mh-artifacts-dir`` - Directory where test artifacts are stored.
