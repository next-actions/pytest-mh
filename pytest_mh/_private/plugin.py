from __future__ import annotations

import inspect
import logging
import sys
import textwrap
from functools import partial, wraps
from os import _exit
from pathlib import Path
from signal import SIGINT, signal
from typing import Callable, Generator, Literal, Type, get_type_hints

import pytest
import yaml

from .artifacts import MultihostArtifactsCollectable, MultihostArtifactsType
from .data import MultihostItemData
from .errors import TeardownExceptionGroup
from .fixtures import MultihostFixture
from .logging import MultihostLogger
from .marks import KnownTopologyBase, TopologyMark
from .multihost import (
    MultihostArtifactsMode,
    MultihostConfig,
    MultihostHost,
    MultihostReentrantUtility,
    MultihostRole,
    mh_utility_enter_dependencies,
    mh_utility_exit_dependencies,
    mh_utility_setup_dependencies,
    mh_utility_teardown_dependencies,
)
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
        self.current_mh: MultihostFixture | None = None
        self.current_topology: str | None = None
        self.required_hosts: list[MultihostHost] = []
        self.pytest_session: pytest.Session | None = None

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
        self.mh_ignore_preferred_topology: bool = pytest_config.getoption("mh_ignore_preferred_topology")

        # Read --mh-collect-logs, default to --mh-collect-artifacts
        self.mh_collect_logs: MultihostArtifactsMode = pytest_config.getoption("mh_collect_logs")
        if self.mh_collect_logs is None:
            self.mh_collect_logs = self.mh_collect_artifacts

        # pytest options
        self.pytest_opt_collect_only: bool = pytest_config.getoption("collectonly")

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

    def sigint_handler(self, sig, frame) -> None:
        # This should not happen
        if self.multihost is None:
            self.logger.error("multihost can not be None, terminating")
            exit(1)

        # User really wants to exit now, ignore teardown
        if self.multihost._sigint:
            self.logger.info(
                "SIGINT received, terminating immediately. "
                "Teardown was not run, therefore hosts are in undefined state."
            )
            _exit(1)

        self.multihost._sigint = True

        # If we are in test, we can terminate gracefully immediately. Teardowns will run.
        if self.multihost._in_test:
            pytest.skip("SIGINT received, aborting running test.")

        # Otherwise we have to wait for setup/teardown to finish
        self.logger.info("")
        self.logger.info("")
        self.logger.info("SIGINT received SIGINT, I will finish current test and exit gracefully.")
        self.logger.info(
            "If you want to exit immediately, press CTRL-C one more time. "
            "In this case, however, hosts will end up in an undefined state "
            "since teardown methods will not run completely."
        )
        self.logger.info("")

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
        self.pytest_session = session

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
        self.logger.info(f"  ignore-preferred-topology: {self.mh_ignore_preferred_topology}")
        self.logger.info("")

        signal(SIGINT, self.sigint_handler)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
        """
        Teardown the module.

        :meta private:
        """
        if self.multihost is None:
            return

        # Run pytest_teardown on all hosts required by selected tests
        if not self.pytest_opt_collect_only:
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

    @pytest.hookimpl(hookwrapper=True)
    def pytest_collection_finish(self, session: pytest.Session) -> Generator:
        # Log required hosts
        self.logger.info("")
        self.logger.info("")
        self.logger.info(self._fmt_bold("Selected tests will use the following hosts:"))
        for host in self.required_hosts:
            self.logger.info(f"  {host.role}: {host.hostname}")
        self.logger.info("")

        yield

        # Run pytest_setup on all hosts required by selected tests
        if not self.pytest_opt_collect_only:
            # Connect to all required hosts to fail quickly if some connection
            # cannot be established.
            if self.multihost is not None and not self.multihost.lazy_ssh:
                for host in self.required_hosts:
                    host.conn.connect()

            self._setup_hosts(self.required_hosts)

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

        if self.multihost._sigint:
            pytest.exit("Aborted because SIGINT was received.")

        # Execute per-topology setup if topology is switched.
        if self._topology_switch(None, item):
            self.current_topology = mark.name
            self._setup_topology(mark.name, mark.controller)

        if not mark.controller._op_state.check_success("topology_setup"):
            pytest.skip("Error in topology setup")

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

            self.current_mh = mh
            data.topology_mark.apply(mh, item.funcargs)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_teardown(self, item: pytest.Item, nextitem: pytest.Item | None) -> Generator:
        """
        Teardown topology if we detect a topology switch.

        :meta private:
        """
        # Inner teardown callback may raise error, but we still need to call
        # topology teardown if needed.
        try:
            yield
        finally:
            self.current_mh = None

            if self.multihost is None:
                return

            data: MultihostItemData | None = MultihostItemData.GetData(item)
            if data is None or data.topology_mark is None:
                return
            mark: TopologyMark = data.topology_mark

            # Execute per-topology teardown if topology changed.
            if self._topology_switch(item, nextitem) or self.multihost._sigint:
                self._teardown_topology(mark.name, mark.controller)

    @pytest.hookimpl(tryfirst=True)
    def pytest_report_teststatus(
        self, report: pytest.CollectReport | pytest.TestReport, config: pytest.Config
    ) -> tuple[str, str, str | tuple[str, dict[str, bool]]] | None:
        if report.when != "call":
            return None

        if hasattr(report, "_pytest_mh__teststatus"):
            return report._pytest_mh__teststatus

        if self.current_mh is None:
            return None

        # Store current outcome in case it is changed by the hook
        original_outcome = report.outcome

        status = self.current_mh._pytest_report_teststatus(report, config)
        setattr(report, "_pytest_mh__teststatus", status)

        # If the outcome is changed and failed, count it towards failures.
        if original_outcome != report.outcome and report.failed:
            if self.pytest_session is not None:
                self.pytest_session.testsfailed += 1

        return status

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

    def _can_run_preferred_topology(self, mark: pytest.Mark, current_topology: str, item: pytest.Item) -> bool:
        if len(mark.args) != 1:
            raise ValueError(
                f"{item.nodeid}: Unexpected number of arguments to pytest.mark.preferred_topology: "
                f"got {len(mark.args)}, expected 1"
            )

        arg = mark.args[0]

        if isinstance(arg, KnownTopologyBase):
            name = arg.value.name
        elif isinstance(arg, TopologyMark):
            name = arg.name
        elif isinstance(arg, str):
            name = arg
        else:
            raise ValueError(
                f"{item.nodeid}: Unexpected type of pytest.mark.preferred_topology: "
                f"got {type(arg)}, expected KnownTopologyBase | TopologyMark | str"
            )

        if name == current_topology:
            return True

        return False

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

        # Run only for preferred topology unless specific topology is requested or the marker is ignored
        if not self.mh_topology and not self.mh_ignore_preferred_topology:
            preferred_topology = item.get_closest_marker(name="preferred_topology")
            if preferred_topology is not None and data.topology_mark is not None:
                return self._can_run_preferred_topology(preferred_topology, data.topology_mark.name, item)

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
            outcome: MultihostOutcome = "error"
            try:
                try:
                    host.logger.phase(f"PYTEST SETUP HOST UTILS :: {host.hostname}")
                    mh_utility_setup_dependencies(host, [MultihostReentrantUtility])
                    host._op_state.set_success("pytest_setup_utils")
                finally:
                    host.logger.phase(f"PYTEST SETUP HOST UTILS DONE :: {host.hostname}")

                try:
                    host.logger.phase(f"PYTEST SETUP :: {host.hostname}")
                    host.pytest_setup()
                    host._op_state.set_success("pytest_setup")
                    outcome = "passed"
                finally:
                    host.logger.phase(f"PYTEST SETUP DONE :: {host.hostname}")
            finally:
                self._collect_artifacts(
                    id=host.hostname,
                    hostdir=False,
                    type="pytest_setup",
                    path=f"hosts/{host.hostname}/pytest_setup",
                    collectable={host: [host, *host._mh_utility_dependencies]},
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
            outcome: MultihostOutcome = "error"
            try:
                try:
                    host.logger.phase(f"PYTEST TEARDOWN :: {host.hostname}")
                    if host._op_state.check_success("pytest_setup"):
                        host.pytest_teardown()
                except Exception as e:
                    errors.append(e)
                finally:
                    host.logger.phase(f"PYTEST TEARDOWN DONE :: {host.hostname}")

                try:
                    host.logger.phase(f"PYTEST TEARDOWN HOST UTILS :: {host.hostname}")
                    mh_utility_teardown_dependencies(host, [MultihostReentrantUtility])
                    outcome = "passed"
                except Exception as e:
                    errors.append(e)
                finally:
                    host.logger.phase(f"PYTEST TEARDOWN HOST UTILS DONE :: {host.hostname}")
            finally:
                self._collect_artifacts(
                    id=host.hostname,
                    hostdir=False,
                    type="pytest_teardown",
                    path=f"hosts/{host.hostname}/pytest_teardown",
                    collectable={host: [host, *host._mh_utility_dependencies]},
                    outcome=outcome,
                    logger=host.logger,
                )

                self.multihost.logger.flush(outcome, f"hosts/{host.hostname}/pytest_teardown.log")

        if errors:
            raise TeardownExceptionGroup("Unable to teardown some hosts (host.pytest_teardown)", errors)

    def _setup_topology(self, name: str, controller: TopologyController) -> None:
        # Silent mypy false positive
        if self.multihost is None:
            raise RuntimeError("Multihost configuration is not present.")

        outcome: MultihostOutcome = "error"
        try:
            try:
                controller.logger.phase(f"TOPOLOGY SETUP ENTER HOST UTILS :: {name}")
                for host in controller.hosts:
                    mh_utility_enter_dependencies(host, "topology_setup")
            finally:
                controller.logger.phase(f"TOPOLOGY SETUP ENTER HOST UTILS DONE :: {name}")

            try:
                controller.logger.phase(f"TOPOLOGY SETUP :: {name}")
                controller._invoke_with_args(controller.set_artifacts)
                controller._invoke_with_args(controller.topology_setup)
                controller._op_state.set_success("topology_setup")
                outcome = "passed"
            finally:
                controller.logger.phase(f"TOPOLOGY SETUP DONE :: {name}")
        finally:
            self._collect_artifacts(
                id=name,
                hostdir=True,
                type="topology_setup",
                path=f"topologies/{name}/topology_setup",
                collectable={x: [x, *x._mh_utility_dependencies, controller] for x in controller.hosts},
                outcome=outcome,
                logger=controller.logger,
            )

            self.multihost.logger.flush(outcome, f"topologies/{name}/topology_setup.log")

    def _teardown_topology(self, name: str, controller: TopologyController) -> None:
        # Silent mypy false positive
        if self.multihost is None:
            raise RuntimeError("Multihost configuration is not present.")

        outcome: MultihostOutcome = "error"
        try:
            errors = []
            try:
                controller.logger.phase(f"TOPOLOGY TEARDOWN :: {name}")
                if controller._op_state.check_success("topology_setup"):
                    controller._invoke_with_args(controller.topology_teardown)
            except Exception as e:
                errors.append(e)
            finally:
                self.current_topology = None
                controller.logger.phase(f"TOPOLOGY TEARDOWN DONE :: {name}")

            controller.logger.phase(f"TOPOLOGY TEARDOWN EXIT HOST UTILS :: {name}")
            for host in controller.hosts:
                try:
                    mh_utility_exit_dependencies(host, "topology_setup")
                except Exception as e:
                    errors.append(e)
            controller.logger.phase(f"TOPOLOGY TEARDOWN EXIT HOST UTILS DONE :: {name}")

            if errors:
                raise TeardownExceptionGroup(
                    "Unable to teardown topology (topology_controller.topology_teardown)", errors
                )

            outcome = "passed"
        finally:
            self._collect_artifacts(
                id=name,
                hostdir=True,
                type="topology_teardown",
                path=f"topologies/{name}/topology_teardown",
                collectable={x: [x, *x._mh_utility_dependencies, controller] for x in controller.hosts},
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
        "--mh-ignore-preferred-topology",
        action="store_true",
        help="All topologies will run, ignore the preferred_topology marker",
    )

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

    config.addinivalue_line(
        "markers",
        "preferred_topology(topology: KnownTopologyBase | TopologyMark | str): "
        "mark test with a preferred topology."
        "Test will execute once, skipping additional topologies",
    )

    config.pluginmanager.register(MultihostPlugin(config), "MultihostPlugin")


def mh_fixture(fixture_function: Callable | None = None, *, scope: Literal["function"] = "function"):
    """
    This creates a function-scoped pytest fixture that can access MultihostRole
    objects that are available to the test directly.

    .. note::

        For this to work correctly, all multihost fixtures have to be correctly
        typed. It will not work without the type hints.

    At this moment, only ``function`` scope is supported.

    .. code-block:: python

        @mh_fixture()
        def my_fixture(client: Client, request: pytest.FixtureRequest):
            pass

        @pytest.mark.topology(KnownTopology.LDAP)
        def test_example(client: Client, ldap: LDAP, my_fixture):
            pass

    :param scope: Fixture scope, defaults to "function"
    :type scope: Literal[&quot;function&quot;], optional
    """

    def decorator(fn):
        full_sig = inspect.signature(fn)
        mh_args = []
        for arg, hint in get_type_hints(fn).items():
            if issubclass(hint, MultihostRole):
                mh_args.append(arg)
                continue

        def call_fixture(mh: MultihostFixture, *args, **kwargs):
            if "mh" in full_sig.parameters:
                kwargs["mh"] = mh

            for arg in mh_args:
                if arg not in mh.fixtures:
                    raise KeyError(f"{fn.__name__}: Parameter {arg} is not a valid topology fixture")

                kwargs[arg] = mh.fixtures[arg]

            return fn(*args, **kwargs)

        @wraps(fn)
        def wrapper_normal(mh: MultihostFixture, *args, **kwargs):
            return call_fixture(mh, *args, **kwargs)

        @wraps(fn)
        def wrapper_yield(mh: MultihostFixture, *args, **kwargs):
            gen = call_fixture(mh, *args, **kwargs)
            yield next(gen)
            try:
                yield next(gen)
            except StopIteration:
                pass

        # Select wrapper
        wrapper = wrapper_normal
        if inspect.isgeneratorfunction(fn):
            wrapper = wrapper_yield

        # Bound multihost parameters
        cb = wraps(fn)(partial(wrapper, **{arg: None for arg in mh_args}))

        # Create pytest fixture
        fixture = pytest.fixture(scope="function")(cb)

        # Mock parameters so they are correctly recognized by pytest fixture
        partial_parameters = [inspect.Parameter("mh", inspect._POSITIONAL_OR_KEYWORD)]
        partial_parameters.extend(
            [param for key, param in full_sig.parameters.items() if key != "mh" and key not in mh_args]
        )

        if hasattr(fixture, "__pytest_wrapped__"):
            obj = fixture.__pytest_wrapped__.obj
        elif hasattr(fixture, "__wrapped__"):
            obj = fixture.__wrapped__
        else:
            raise AttributeError(
                "Fixture object has no __pytest_wrapped__ nor __wrapped__ attribute, "
                "report this to pytest-mh upstream."
            )

        obj.func.__signature__ = inspect.Signature(partial_parameters, return_annotation=full_sig.return_annotation)

        return fixture

    # Direct decoration.
    if fixture_function:
        return decorator(fixture_function)

    return decorator
