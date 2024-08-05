# Configuration file for multihost tests.

from __future__ import annotations

from framework.config import SUDOMultihostConfig

from pytest_mh import MultihostPlugin

# Load additional plugins
pytest_plugins = ("pytest_mh",)


# Setup pytest-mh
def pytest_plugin_registered(plugin) -> None:
    if isinstance(plugin, MultihostPlugin):
        plugin.config_class = SUDOMultihostConfig
