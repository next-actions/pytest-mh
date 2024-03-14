from __future__ import annotations

import inspect
import logging
import sys
import textwrap
from pathlib import Path
from typing import Generator, Type

import pytest
import yaml

from .artifacts import MultihostArtifactsCollectable, MultihostArtifactsType
from .data import MultihostItemData
from .fixtures import MultihostFixture
from .logging import MultihostLogger
from .marks import TopologyMark
from .multihost import MultihostArtifactsMode, MultihostConfig, MultihostHost
from .topology import Topology
from .topology_controller import TopologyController
from .types import MultihostOutcome

MarkStashKey = pytest.StashKey[TopologyMark | None]()


class MultihostPlugin(object):
    """
    Pytest multihost plugin.
    """

    def __init__(self, pytest_config: pytest.Config) -> None:
        self.config_class: Type[MultihostConfig] | None = None
        self.logger: logging.Logger = self._create_logger(pytest_config.option.verbose > 2)
        self.multihost: MultihostConfig | None = None
        self.topology: Topology | None = None
        self.confdict: dict | None = None
        self.current_topology: str | None = None
        self.required_hosts: list[MultihostHost] = []

        # CLI options
        self.mh_config: str = pytest_config.getoption("mh_config")
        self.mh_log_path: str = pytest_config.getoption("mh_log_path")
        self.mh_lazy_ssh: bool = pytest_config.getoption("mh_lazy_ssh")
        self.mh_topology: list[str] = pytest_config.getoption("mh_topology")
        self.mh_not_topology: list[str] = pytest_config.getoption("mh_not_topology")
        self.mh_exact_topology: bool = pytest_config.getoption("mh_exact_topology")
        self.mh_collect_artifacts: MultihostArtifactsMode = pytest_config.getoption("mh_collect_artifacts")
        self.mh_artifacts_dir: Path = Path(pytest_config.getoption("mh_artifacts_dir"))
        self.mh_compress_artifacts: bool = pytest_config.getoption("mh_compress_artifacts")

        # Read --mh-collect-logs, default to --mh-collect-artifacts
        self.mh_collect_logs: MultihostArtifactsMode = pytest_config.getoption("mh_collect_logs")
        if self.mh_collect_logs is None:
            self.mh_collect_logs = self.mh_collect_artifacts

    @classmethod
    def GetLogger(cls) -> logging.Logger:
        """
        Get plugin's logger.
        """

        return logging.getLogger("pytest_mh.plugin")

    def __load_conf(self, path: str) -> dict:
        """
        Load multihost configuration from a yaml file.

        :param path: Path to the yaml file.
        :type path: str
        :raises ValueError: If not file was provided.
        :raises IOError: If unable to read the file.
        :return: Parsed configuration.
        :rtype: dict

        :meta private:
        """
        if not path:
            raise ValueError("You need to provide valid multihost configuration file, use --mh-config=$path")

        try:
            with open(path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise IOError(f'Unable to open multihost configuration "{path}": {str(e)}')

    def setup(self) -> None:
        """
        Read and apply multihost configuration.

        :meta private:
        """
        if self.config_class is None:
            raise ValueError("Set MultihostPlugin.config_class to subclass of MultihostConfig")

        self.confdict = self.__load_conf(self.mh_config)

        logger = MultihostLogger.GetLogger()
        logger.setup(
            log_path=self.mh_log_path,
            artifacts_mode=self.mh_collect_logs,
            artifacts_dir=self.mh_artifacts_dir,
            confdict=self.confdict,
        )

        self.multihost = self.config_class(
            self.confdict,
            logger=logger,
            lazy_ssh=self.mh_lazy_ssh,
            artifacts_dir=self.mh_artifacts_dir,
            artifacts_mode=self.mh_collect_artifacts,
            artifacts_compression=self.mh_compress_artifacts,
        )
        self.topology = Topology.FromMultihostConfig(self.confdict)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        """
        Setup the module and log information about given multihost configuration
        and provided options.

        :meta private:
        """
        # Calling the setup here instead of in constructor to allow running
        # pytest --help and other action-less parameters.
        self.setup()

        # Silent mypy false positive
        if self.topology is None:
            raise ValueError("Topology must be already set!")

        if self.multihost is None:
            self.logger.info(self._fmt_bold("Multihost configuration:"))
            self.logger.info("  No multihost configuration provided.")
            self.logger.info("  Make sure to run tests with --mh-log-path parameter.")
            self.logger.info("")
            return

        self.logger.info(self._fmt_bold("Multihost configuration:"))
        self.logger.info(textwrap.indent(yaml.dump(self.confdict, sort_keys=False), "  "))
        self.logger.info(self._fmt_bold("Detected topology:"))
        self.logger.info(textwrap.indent(yaml.dump(self.topology.export(), sort_keys=False), "  "))
        self.logger.info(self._fmt_bold("Additional settings:"))
        self.logger.info(f"  config file: {self.mh_config}")
        self.logger.info(f"  log path: {self.mh_log_path}")
        self.logger.info(f"  lazy ssh: {self.mh_lazy_ssh}")
        self.logger.info(f"  topology filter: {', '.join(self.mh_topology + [f'!{x}' for x in self.mh_not_topology])}")
        self.logger.info(f"  require exact topology: {self.mh_exact_topology}")
        self.logger.info(f"  collect artifacts: {self.mh_collect_artifacts}")
        self.logger.info(f"  artifacts directory: {self.mh_artifacts_dir}")
        self.logger.info(f"  collect logs: {self.mh_collect_logs}")
        self.logger.info("")

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
        """
        Teardown the module.

        :meta private:
        """
        if self.multihost is None:
            return

        # Run pytest_teardown on all hosts required by selected tests
        self._teardown_hosts(self.required_hosts)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_make_collect_report(self, collector: pytest.Collector) -> Generator[None, pytest.CollectReport, None]:
        """
        If multiple topology marks are present on the collected test, we need to
        parametrize it. In order to do so, the test is replaced with multiple
        clones, one for each topology.

        The topology associated with the test clone is stored in
        ``topology_mark`` property of the clone.

        :meta private:
        """

        outcome = yield
        report = outcome.get_result()

        if not report.result:
            return

        if self.multihost is None:
            return

        new_result = []
        for result in report.result:
            if not isinstance(result, pytest.Function):
                new_result.append(result)
                continue

            has_marks = False
            for mark in self.multihost.TopologyMarkClass.ExpandMarkers(result):
                has_marks = True
                topology_mark = self.multihost.TopologyMarkClass.Create(result, mark)
                f = self._clone_function(f"{result.name} ({topology_mark.name})", result)
                f.stash[MarkStashKey] = topology_mark
                new_result.append(f)

            if not has_marks:
                result.stash[MarkStashKey] = None
                new_result.append(result)

        report.result = new_result

    @pytest.hookimpl(hookwrapper=True)
    def pytest_collection_modifyitems(self, config: pytest.Config, items: list[pytest.Item]) -> Generator:
        """
        Filter collected items and deselect these that can not be run on the
        selected multihost configuration.

        Internal plugin's data are stored in ``multihost`` property of each
        :class:`pytest.Item`.

        :meta private:
        """
        data: MultihostItemData | None = None
        selected: list[pytest.Item] = []
        deselected: list[pytest.Item] = []
        mapping: dict[str, list[pytest.Item]] = {}

        # Silent mypy false positive
        if self.multihost is None:
            return

        for item in items:
            data = MultihostItemData(self.multihost, item.stash[MarkStashKey]) if self.multihost else None
            MultihostItemData.SetData(item, data)

            if not self._can_run_test(item, data):
                deselected.append(item)
                continue

            # This test can be run, perform delayed initialization of data.
            if data is not None:
                data._init()

            # Map test items by topology name so we can sort them later
            if data is None or data.topology_mark is None:
                mapping.setdefault("", []).append(item)
            else:
                mapping.setdefault(data.topology_mark.name, []).append(item)

        # Sort test by topology name
        selected = sum([y for _, y in sorted(mapping.items())], [])

        # Yield result to pytest
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected

        yield

        # List of items may have been further modified by other plugins or filters
        # Remember all hosts required to run selected tests
        required_hosts_set: set[MultihostHost] = set()
        for item in items:
            data = MultihostItemData.GetData(item)
            if data is None or data.topology_mark is None:
                continue

            required_hosts_set.update(self.multihost.topology_hosts(data.topology_mark.topology))

        # Sort required host by name to provide deterministic runs
        self.required_hosts = sorted(required_hosts_set, key=lambda x: x.hostname)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        """
        Create fixtures requested in :class:`~pytest_mh.TopologyMark`
        (``@pytest.mark.topology``). It adds the fixture names into ``funcargs``
        property of the pytest item in order to make them available.

        At this step, the fixtures do not have any value. The value is assigned
        later in :func:`pytest_runtest_call` hook.

        :meta private:
        """
        if not isinstance(item, pytest.Function):
            return

        data: MultihostItemData | None = MultihostItemData.GetData(item)
        if self.multihost is None or data is None or data.topology_mark is None:
            return
        mark: TopologyMark = data.topology_mark

        # Run pytest_setup on all hosts required by selected tests
        self._setup_hosts(self.required_hosts)

        # Execute per-topology setup if topology is switched.
        if self._topology_switch(None, item):
            self.current_topology = mark.name
            self._setup_topology(mark.name, mark.controller)

        # Make mh fixture always available
        if "mh" not in item.fixturenames:
            item.fixturenames.append("mh")

        # Fill in parameters that will be set later in pytest_runtest_call hook,
        # otherwise pytest will raise unknown fixture error.
        spec = inspect.getfullargspec(item.obj)
        for arg in mark.args:
            if arg in spec.args:
                item.funcargs[arg] = None

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_call(self, item: pytest.Item) -> None:
        """
        Assign values to dynamically created multihost fixtures.

        :meta private:
        """
        if not isinstance(item, pytest.Function):
            return

        data: MultihostItemData | None = MultihostItemData.GetData(item)
        if data is None:
            return

        if data.topology_mark is not None:
            mh = item.funcargs["mh"]
            if not isinstance(mh, MultihostFixture):
                raise ValueError(f"Fixture mh is not MultihostFixture but {type(mh)}!")

            data.topology_mark.apply(mh, item.funcargs)

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_teardown(self, item: pytest.Item, nextitem: pytest.Item | None) -> None:
        """
        Teardown topology if we detect a topology switch.

        :meta private:
        """
        if self.multihost is None:
            return

        data: MultihostItemData | None = MultihostItemData.GetData(item)
        if data is None or data.topology_mark is None:
            return
        mark: TopologyMark = data.topology_mark

        # Execute per-topology teardown if topology changed.
        if self._topology_switch(item, nextitem):
            self._teardown_topology(mark.name, mark.controller)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(
        self, item: pytest.Item, call: pytest.CallInfo[None]
    ) -> Generator[None, pytest.TestReport, None]:
        """
        Store test outcome in multihost data: item.multihost.outcome. The outcome
        can be 'passed', 'failed' or 'skipped'.
        """
        outcome = yield

        data: MultihostItemData | None = MultihostItemData.GetData(item)
        result: pytest.TestReport = outcome.get_result()

        if data is None:
            raise RuntimeError("MultihostItemData should not be None")

        if result.when != "call":
            return

        data.outcome = result.outcome
        data.result = result

    # Hook from pytest-output plugin
    @pytest.hookimpl(optionalhook=True)
    def pytest_output_item_collected(self, config: pytest.Config, item) -> None:
        try:
            from pytest_output.output import OutputDataItem
        except ImportError:
            pass

        if not isinstance(item, OutputDataItem):
            raise ValueError(f"Unexpected item type: {type(item)}")

        data: MultihostItemData | None = MultihostItemData.GetData(item.item)
        if data is None or data.topology_mark is None:
            return

        item.extra.setdefault("pytest-mh", {})["Topology"] = data.topology_mark.name

    def _fmt_color(self, text: str, color: str) -> str:
        if sys.stdout.isatty():
            reset = "\033[0m"
            return f"{color}{text}{reset}"

        return text

    def _fmt_bold(self, text: str) -> str:
        return self._fmt_color(text, "\033[1m")

    def _create_logger(self, verbose) -> logging.Logger:
        stdout = logging.StreamHandler(sys.stdout)
        stdout.setLevel(logging.DEBUG)
        stdout.setFormatter(logging.Formatter("%(message)s"))

        logger = self.GetLogger()
        logger.addHandler(stdout)
        logger.setLevel(logging.DEBUG if verbose else logging.INFO)

        return logger

    def _is_multihost_required(self, item: pytest.Item) -> bool:
        return item.get_closest_marker(name="topology") is not None

    def _can_run_test(self, item: pytest.Item, data: MultihostItemData | None) -> bool:
        if data is None:
            return not self._is_multihost_required(item)

        if self.topology is None:
            raise ValueError("Topology must be already set!")

        if data.topology_mark is not None:
            if self.mh_exact_topology:
                if data.topology_mark.topology != self.topology:
                    return False
            else:
                if not self.topology.satisfies(data.topology_mark.topology):
                    return False

        if self.mh_not_topology:
            if data.topology_mark is not None and data.topology_mark.name in self.mh_not_topology:
                return False

        if self.mh_topology:
            if data.topology_mark is None:
                return False

            if data.topology_mark.name not in self.mh_topology:
                return False

        return True

    def _clone_function(self, name: str, f: pytest.Function) -> pytest.Function:
        callspec = f.callspec if hasattr(f, "callspec") else None

        return pytest.Function.from_parent(
            parent=f.parent,
            name=name,
            callspec=callspec,
            callobj=f.obj,
            keywords=f.keywords,
            fixtureinfo=f._fixtureinfo,
            originalname=f.originalname,
        )

    def _topology_switch(self, curitem: pytest.Item | None, nextitem: pytest.Item | None) -> bool:
        # No more items means topology switch for our usecase
        if nextitem is None:
            return True

        # If current item is None, we need to check current topology
        if curitem is None:
            # This is a first test in the new topology
            if self.current_topology is None:
                return True
            # We always set current_topology to None when switching topologies
            else:
                return False

        curdata: MultihostItemData | None = MultihostItemData.GetData(curitem)
        nextdata: MultihostItemData | None = MultihostItemData.GetData(nextitem)

        if curdata is None or nextdata is None:
            raise RuntimeError("Data can not be None")

        # If the test does not have topology marker, we consider it a switch
        if curdata.topology_mark is None or nextdata.topology_mark is None:
            return True

        # Different topology name is a switch
        if curdata.topology_mark.name != nextdata.topology_mark.name:
            return True

        return False

    def _setup_hosts(self, hosts: list[MultihostHost]) -> None:
        # Silent mypy false positive
        if self.multihost is None:
            raise RuntimeError("Multihost configuration is not present.")

        for host in hosts:
            try:
                host.logger.phase(f"PYTEST SETUP :: {host.hostname}")
                host.pytest_setup()
                host._op_state.set_success("pytest_setup")
            finally:
                host.logger.phase(f"PYTEST SETUP DONE :: {host.hostname}")
                outcome: MultihostOutcome = "error"
                if host._op_state.check_success("pytest_setup"):
                    outcome = "passed"

                self._collect_artifacts(
                    id=host.hostname,
                    hostdir=False,
                    type="pytest_setup",
                    path=f"hosts/{host.hostname}/pytest_setup",
                    collectable={host: [host]},
                    outcome=outcome,
                    logger=host.logger,
                )

                self.multihost.logger.flush(outcome, f"hosts/{host.hostname}/pytest_setup.log")

    def _teardown_hosts(self, hosts: list[MultihostHost]) -> None:
        # Silent mypy false positive
        if self.multihost is None:
            raise RuntimeError("Multihost configuration is not present.")

        errors = []
        for host in hosts:
            if host._op_state.check_success("pytest_setup"):
                try:
                    host.logger.phase(f"PYTEST TEARDOWN :: {host.hostname}")
                    host.pytest_teardown()
                    host._op_state.set_success("pytest_teardown")
                except Exception as e:
                    errors.append(e)
                finally:
                    host.logger.phase(f"PYTEST TEARDOWN DONE :: {host.hostname}")
                    outcome: MultihostOutcome = "error"
                    if host._op_state.check_success("pytest_teardown"):
                        outcome = "passed"

                    self._collect_artifacts(
                        id=host.hostname,
                        hostdir=False,
                        type="pytest_teardown",
                        path=f"hosts/{host.hostname}/pytest_teardown",
                        collectable={host: [host]},
                        outcome=outcome,
                        logger=host.logger,
                    )

                    self.multihost.logger.flush(outcome, f"hosts/{host.hostname}/pytest_teardown.log")

        if errors:
            raise Exception(errors)

    def _setup_topology(self, name: str, controller: TopologyController) -> None:
        # Silent mypy false positive
        if self.multihost is None:
            raise RuntimeError("Multihost configuration is not present.")

        try:
            controller.logger.phase(f"TOPOLOGY SETUP :: {name}")
            controller._invoke_with_args(controller.set_artifacts)
            controller._invoke_with_args(controller.topology_setup)
            controller._op_state.set_success("topology_setup")
        finally:
            controller.logger.phase(f"TOPOLOGY SETUP DONE :: {name}")
            outcome: MultihostOutcome = "error"
            if controller._op_state.check_success("topology_setup"):
                outcome = "passed"

            self._collect_artifacts(
                id=name,
                hostdir=True,
                type="topology_setup",
                path=f"topologies/{name}/topology_setup",
                collectable={x: [x, controller] for x in controller.hosts},
                outcome=outcome,
                logger=controller.logger,
            )

            self.multihost.logger.flush(outcome, f"topologies/{name}/topology_setup.log")

    def _teardown_topology(self, name: str, controller: TopologyController) -> None:
        # Silent mypy false positive
        if self.multihost is None:
            raise RuntimeError("Multihost configuration is not present.")

        try:
            if controller._op_state.check_success("topology_setup"):
                controller.logger.phase(f"TOPOLOGY TEARDOWN :: {name}")
                controller._invoke_with_args(controller.topology_teardown)
                controller._op_state.set_success("topology_teardown")
        finally:
            self.current_topology = None
            controller.logger.phase(f"TOPOLOGY TEARDOWN DONE :: {name}")
            outcome: MultihostOutcome = "error"
            if controller._op_state.check_success("topology_teardown"):
                outcome = "passed"

            self._collect_artifacts(
                id=name,
                hostdir=True,
                type="topology_teardown",
                path=f"topologies/{name}/topology_teardown",
                collectable={x: [x, controller] for x in controller.hosts},
                outcome=outcome,
                logger=controller.logger,
            )

            self.multihost.logger.flush(outcome, f"topologies/{name}/topology_teardown.log")

    def _collect_artifacts(
        self,
        *,
        id: str,
        hostdir: bool,
        type: MultihostArtifactsType,
        path: str,
        collectable: dict[MultihostHost, list[MultihostArtifactsCollectable]],
        outcome: MultihostOutcome,
        logger: MultihostLogger,
    ) -> None:
        logger.phase(f"COLLECT ARTIFACTS :: {id}")
        for host, objects in collectable.items():
            dest = f"{path}/{host.hostname}" if hostdir else path
            try:
                host.artifacts_collector.collect(type, path=dest, outcome=outcome, collect_objects=objects)
            except Exception as e:
                self.logger.error(
                    "An error happend when collecting artifacts",
                    extra={
                        "data": {
                            "Error message": str(e),
                        }
                    },
                )
        logger.phase(f"COLLECT ARTIFACTS DONE :: {id}")


# These pytest hooks must be available outside of the plugin's class because
# they are executed before the plugin is registered.


def pytest_addoption(parser):
    """
    Pytest hook: add command line options.
    """

    parser.addoption("--mh-config", action="store", help="Path to the multihost configuration file")

    parser.addoption("--mh-log-path", action="store", help="Path to store multihost logs")

    parser.addoption("--mh-lazy-ssh", action="store_true", help="Postpone connecting to host SSH until it is required")

    parser.addoption(
        "--mh-topology",
        action="append",
        default=[],
        help="Filter tests by given topology, can be set multiple times",
    )

    parser.addoption(
        "--mh-not-topology",
        action="append",
        default=[],
        help="Do not run tests for given topology, can be set multiple times",
    )

    parser.addoption(
        "--mh-exact-topology",
        action="store_true",
        help="Test will be deselected if its topology does not match given multihost config exactly",
    )

    parser.addoption(
        "--mh-collect-artifacts",
        action="store",
        default="on-failure",
        nargs="?",
        choices=["never", "on-failure", "always"],
        help="Collect artifacts after test run (default: %(default)s)",
    )

    parser.addoption(
        "--mh-artifacts-dir",
        action="store",
        default="./artifacts",
        help="Directory where artifacts will be stored (default: %(default)s)",
    )

    parser.addoption(
        "--mh-compress-artifacts",
        action="store_true",
        help="If set, test artifacts are stored in a compressed archive",
    )

    parser.addoption(
        "--mh-collect-logs",
        action="store",
        default=None,
        nargs="?",
        choices=["never", "on-failure", "always"],
        help="Collect logs mode (default: use value of --mh-collect-artifacts)",
    )


def pytest_configure(config: pytest.Config):
    """
    Pytest hook: register multihost plugin.
    """

    # register additional markers
    config.addinivalue_line(
        "markers",
        "topology(name: str, topology: pytest_mh.Topology, domains: dict[str, str], /, "
        + "*, fixture1=target1, ...): topology required to run the test",
    )

    config.addinivalue_line(
        "markers",
        "require(condition, reason): evaluate condition, parameters may be topology fixture, "
        "the test is skipped if condition is not met",
    )

    config.pluginmanager.register(MultihostPlugin(config), "MultihostPlugin")
