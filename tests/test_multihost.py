from __future__ import annotations

from pathlib import Path
from typing import Type

import pytest
from pytest_mock import MockerFixture

from pytest_mh import (
    MultihostConfig,
    MultihostDomain,
    MultihostFixture,
    MultihostHost,
    MultihostLogger,
    MultihostReentrantUtility,
    MultihostRole,
    MultihostUtility,
    TopologyMark,
    mh_utility_ignore_use,
)
from pytest_mh._private.multihost import mh_utility_setup, mh_utility_teardown
from pytest_mh.conn import Bash
from pytest_mh.conn.container import ContainerClient
from pytest_mh.conn.ssh import SSHClient


@pytest.fixture
def mock_config(mocker: MockerFixture) -> MultihostConfig:
    mock_logger = mocker.MagicMock(spec=MultihostLogger)
    mock_config = mocker.MagicMock(spec=MultihostConfig)
    mock_config.logger = mock_logger
    mock_config.lazy_ssh = True
    mock_config.artifacts_dir = Path("artifacts")
    mock_config.artifacts_mode = "always"
    mock_config.artifacts_compression = False

    return mock_config


@pytest.fixture
def mock_domain(mocker: MockerFixture, mock_config: MultihostConfig) -> MultihostDomain:
    mock_domain = mocker.MagicMock(spec=MultihostDomain)
    mock_domain.mh_config = mock_config
    mock_domain.logger = mock_config.logger

    return mock_domain


@pytest.fixture
def mock_host(mock_domain: MultihostDomain) -> MultihostHost:
    return MultihostHostMock(mock_domain, dict(hostname="test.example", role="test"))


@pytest.fixture
def mock_mh(mocker: MockerFixture) -> MultihostFixture:
    return mocker.MagicMock(spec=MultihostFixture)


class MultihostConfigMock(MultihostConfig):
    @property
    def id_to_domain_class(self) -> dict[str, Type[MultihostDomain]]:
        return {
            "*": MultihostDomainMock,
        }


class MultihostDomainMock(MultihostDomain[MultihostConfig]):
    @property
    def role_to_host_class(self) -> dict[str, Type[MultihostHost]]:
        return {
            "*": MultihostHostMock,
        }

    @property
    def role_to_role_class(self) -> dict[str, Type[MultihostRole]]:
        """
        Map role to role class. Asterisk ``*`` can be used as fallback value.

        :rtype: Class name.
        """
        return {
            "*": MultihostRoleMock,
        }


class MultihostHostMock(MultihostHost[MultihostDomain[MultihostConfig]]):
    pass


class MultihostRoleMock(MultihostRole[MultihostHost[MultihostDomain[MultihostConfig]]]):
    pass


class MultihostUtilityMock(MultihostUtility[MultihostHost]):
    pass


def test_multihost__MultihostConfig_init(mocker: MockerFixture):
    mock_logger = mocker.MagicMock(spec=MultihostLogger)

    confdict = {
        "config": {
            "custom-config": True,
        },
        "domains": [
            {
                "id": "test",
                "hosts": [
                    {
                        "hostname": "test.example",
                        "role": "test",
                    }
                ],
            }
        ],
    }

    config = MultihostConfigMock(
        confdict,
        logger=mock_logger,
        lazy_ssh=True,
        artifacts_dir=Path("artifacts"),
        artifacts_mode="always",
        artifacts_compression=False,
    )

    assert config.confdict == confdict
    assert config.config == confdict["config"]
    assert config.logger is mock_logger
    assert config.lazy_ssh is True
    assert config.artifacts_dir == Path("artifacts")
    assert config.artifacts_mode == "always"
    assert config.artifacts_compression is False
    assert config.required_fields == ["domains"]
    assert config.TopologyMarkClass is TopologyMark

    assert len(config.domains) == 1
    assert config.domains[0].id == "test"

    assert len(config.domains[0].hosts) == 1
    assert config.domains[0].hosts[0].hostname == "test.example"
    assert config.domains[0].hosts[0].role == "test"
    assert config.domains[0].hosts[0].conn.connected is False


def test_multihost__MultihostConfig_init__missing_domains(mocker: MockerFixture):
    mock_logger = mocker.MagicMock(spec=MultihostLogger)

    confdict = {
        "config": {
            "custom-config": True,
        }
    }

    with pytest.raises(ValueError, match='"domains"'):
        MultihostConfigMock(
            confdict,
            logger=mock_logger,
            lazy_ssh=True,
            artifacts_dir=Path("artifacts"),
            artifacts_mode="always",
            artifacts_compression=False,
        )


def test_multihost__MultihostConfig_init__missing_custom_required_fields(mocker: MockerFixture):
    mock_logger = mocker.MagicMock(spec=MultihostLogger)

    confdict = {
        "domains": [
            {
                "id": "test",
                "hosts": [
                    {
                        "hostname": "test.example",
                        "role": "test",
                    }
                ],
            }
        ],
    }

    mock_required_fields = mocker.patch.object(
        MultihostConfigMock, "required_fields", new_callable=mocker.PropertyMock
    )
    mock_required_fields.return_value = ["domains", "config/custom-config"]
    with pytest.raises(ValueError, match='"config/custom-config"'):
        MultihostConfigMock(
            confdict,
            logger=mock_logger,
            lazy_ssh=True,
            artifacts_dir=Path("artifacts"),
            artifacts_mode="always",
            artifacts_compression=False,
        )


def test_multihost__MultihostDomain_init(mock_config: MultihostConfig):
    confdict = {
        "config": {
            "custom-config": True,
        },
        "id": "test",
        "hosts": [
            {
                "hostname": "test.example",
                "role": "test",
            }
        ],
    }

    domain = MultihostDomainMock(
        mock_config,
        confdict,
    )

    assert domain.confdict == confdict
    assert domain.config == confdict["config"]
    assert domain.mh_config is mock_config
    assert domain.logger is mock_config.logger
    assert domain.id == "test"
    assert domain.roles == ["test"]

    assert len(domain.hosts) == 1
    assert domain.hosts[0].hostname == "test.example"
    assert domain.hosts[0].role == "test"
    assert domain.hosts[0].conn.connected is False


def test_multihost__MultihostDomain_init__missing_required_fileds(mock_config: MultihostConfig):
    confdict: dict = dict()

    with pytest.raises(ValueError, match='"id"'):
        confdict = {
            "hosts": [
                {
                    "hostname": "test.example",
                    "role": "test",
                }
            ],
        }

        MultihostDomainMock(
            mock_config,
            confdict,
        )

    with pytest.raises(ValueError, match='"hosts"'):
        confdict = {
            "id": "test",
        }

        MultihostDomainMock(
            mock_config,
            confdict,
        )


def test_multihost__MultihostDomain_init__missing_custom_required_fields(
    mocker: MockerFixture, mock_config: MultihostConfig
):
    confdict = {
        "id": "test",
        "hosts": [
            {
                "hostname": "test.example",
                "role": "test",
            }
        ],
    }

    mock_required_fields = mocker.patch.object(
        MultihostDomainMock, "required_fields", new_callable=mocker.PropertyMock
    )
    mock_required_fields.return_value = ["id", "hosts", "config/custom-config"]

    with pytest.raises(ValueError, match='"config/custom-config"'):
        MultihostDomainMock(
            mock_config,
            confdict,
        )


def test_multihost__MultihostDomain_hosts_by_role(mock_config: MultihostConfig):
    confdict = {
        "id": "test",
        "hosts": [
            {
                "hostname": "test.example",
                "role": "test",
            }
        ],
    }

    domain = MultihostDomainMock(
        mock_config,
        confdict,
    )

    hosts = domain.hosts_by_role("test")
    assert hosts == [domain.hosts[0]]

    hosts = domain.hosts_by_role("unknown")
    assert not hosts


def test_multihost__MultihostHost_init(mock_domain: MultihostDomain):
    confdict = {
        "hostname": "test.example",
        "role": "test",
        "config": {
            "custom-config": True,
        },
    }

    host = MultihostHostMock(
        mock_domain,
        confdict,
    )

    assert host.confdict == confdict
    assert host.config == confdict["config"]
    assert host.mh_domain is mock_domain
    assert host.role == "test"
    assert host.hostname == "test.example"
    assert host.os_family.value == "linux"
    assert isinstance(host.shell, Bash)


def test_multihost__MultihostHost_init__missing_required_fileds(mock_domain: MultihostDomain):
    with pytest.raises(ValueError, match='"role"'):
        confdict = {
            "hostname": "test.example",
        }

        MultihostHostMock(
            mock_domain,
            confdict,
        )

    with pytest.raises(ValueError, match='"hostname"'):
        confdict = {
            "role": "test",
        }

        MultihostHostMock(
            mock_domain,
            confdict,
        )


def test_multihost__MultihostHost_init__missing_custom_required_fields(
    mocker: MockerFixture, mock_domain: MultihostDomain
):
    confdict = {
        "hostname": "test.example",
        "role": "test",
    }

    mock_required_fields = mocker.patch.object(MultihostHostMock, "required_fields", new_callable=mocker.PropertyMock)
    mock_required_fields.return_value = ["role", "hostname", "config/custom-config"]

    with pytest.raises(ValueError, match='"config/custom-config"'):
        MultihostHostMock(
            mock_domain,
            confdict,
        )


@pytest.mark.parametrize(
    "config, expected, engine",
    [
        pytest.param({}, SSHClient, None, id="default"),
        pytest.param(dict(conn=dict(type="ssh")), SSHClient, None, id="ssh"),
        pytest.param(dict(conn=dict(type="podman", container="test")), ContainerClient, "podman", id="podman"),
        pytest.param(dict(conn=dict(type="docker", container="test")), ContainerClient, "docker", id="docker"),
    ],
)
def test_multihost__MultihostHost_get_connection(mock_domain: MultihostDomain, config, expected, engine):
    confdict = {
        "hostname": "test.example",
        "role": "test",
        **config,
    }

    host = MultihostHostMock(
        mock_domain,
        confdict,
    )

    conn = host.get_connection()
    assert isinstance(conn, expected)
    if engine is not None:
        assert conn.engine == engine


def test_multihost__MultihostHost_dependencies(mock_domain: MultihostDomain):
    confdict = {
        "hostname": "test.example",
        "role": "test",
    }

    class DependencyBase(MultihostReentrantUtility):
        def __enter__(self):
            pass

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    class Dependency1(DependencyBase):
        pass

    class Dependency2(DependencyBase):
        pass

    class Dependency3(DependencyBase):
        def __init__(self, host, dep1: Dependency1, dep2: Dependency2):
            super().__init__(host)
            self.dep1 = dep1
            self.dep2 = dep2

    class NotADependency(MultihostUtility):
        def __init__(self, host):
            super().__init__(host)

    class DependencyHost(MultihostHostMock):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            self.dep1 = Dependency1(self)
            self.dep2 = Dependency2(self)
            self.dep3 = Dependency3(self, self.dep1, self.dep2)
            self.dep2_again = Dependency2(self)
            self.notdep = NotADependency(self)

    host = DependencyHost(
        mock_domain,
        confdict,
    )

    # same classes do not have deterministic order
    order1 = [host.dep1, host.dep2, host.dep2_again, host.dep3]
    order2 = [host.dep1, host.dep2_again, host.dep2, host.dep3]
    assert host._mh_utility_dependencies == order1 or host._mh_utility_dependencies == order2


def test_multihost__MultihostRole_init(mock_host: MultihostHost, mock_mh: MultihostFixture):
    role = MultihostRoleMock(mock_mh, "test", mock_host)

    assert role.mh is mock_mh
    assert role.host is mock_host
    assert role.logger is mock_host.logger
    assert role.role == "test"
    assert not role.artifacts


def test_multihost__MultihostRole_dependencies(mock_host: MultihostHost, mock_mh: MultihostFixture):
    class DependencyBase(MultihostReentrantUtility):
        def __enter__(self):
            pass

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    class Dependency1(DependencyBase):
        pass

    class Dependency2(DependencyBase):
        pass

    class Dependency3(DependencyBase):
        def __init__(self, host, dep1: Dependency1, dep2: Dependency2):
            super().__init__(host)
            self.dep1 = dep1
            self.dep2 = dep2

    class Dependency4(MultihostUtility):
        def __init__(self, host):
            super().__init__(host)

    class DependencyRole(MultihostRoleMock):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            self.dep1 = Dependency1(self)
            self.dep2 = Dependency2(self)
            self.dep3 = Dependency3(self, self.dep1, self.dep2)
            self.dep2_again = Dependency2(self)
            self.dep4 = Dependency4(self)

    role = DependencyRole(mock_mh, "test", mock_host)

    # same classes do not have deterministic order
    order1 = [role.dep1, role.dep2, role.dep2_again, role.dep4, role.dep3]
    order2 = [role.dep1, role.dep2_again, role.dep2, role.dep4, role.dep3]
    assert role._mh_utility_dependencies == order1 or role._mh_utility_dependencies == order2


def test_multihost__MultihostUtility_init(mock_host: MultihostHost):
    util = MultihostUtilityMock(mock_host)

    assert util.host is mock_host
    assert util.logger is mock_host.logger
    assert not util.artifacts

    assert util._mh_utility_call_setup is False
    assert util._mh_utility_call_teardown is False
    assert util._mh_utility_used is False
    assert not util._mh_utility_dependencies


def test_multihost__MultihostUtility_meta__call_setup_teardown(mock_host: MultihostHost):
    class UtilitySetup(MultihostUtilityMock):
        def setup(self):
            return super().setup()

    class UtilityTeardown(MultihostUtilityMock):
        def teardown(self):
            return super().teardown()

    class UtilitySetupTeardown(UtilitySetup, UtilityTeardown):
        pass

    util: MultihostUtility = UtilitySetup(mock_host)
    assert util._mh_utility_call_setup is True
    assert util._mh_utility_call_teardown is False

    util = UtilityTeardown(mock_host)
    assert util._mh_utility_call_setup is False
    assert util._mh_utility_call_teardown is True

    util = UtilitySetupTeardown(mock_host)
    assert util._mh_utility_call_setup is True
    assert util._mh_utility_call_teardown is True


def test_multihost__MultihostUtility_meta__used(mock_host: MultihostHost):
    class Utility(MultihostUtilityMock):
        @property
        def prop(self):
            return "prop"

        def test(self):
            pass

        @mh_utility_ignore_use
        def ignore(self):
            pass

    util = Utility(mock_host).postpone_setup()
    assert util._mh_utility_used is False
    util.test()
    assert util._mh_utility_used is True

    util = Utility(mock_host).postpone_setup()
    assert util._mh_utility_used is False
    _ = util.prop
    assert util._mh_utility_used is True

    util = Utility(mock_host).postpone_setup()
    assert util._mh_utility_used is False
    util.ignore()
    assert util._mh_utility_used is False


def test_multihost__MultihostUtility_dependencies(mock_host: MultihostHost):
    class DependencyBase(MultihostReentrantUtility):
        def __enter__(self):
            pass

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    class Dependency1(DependencyBase):
        pass

    class Dependency2(DependencyBase):
        pass

    class Dependency3(DependencyBase):
        def __init__(self, host, dep1: Dependency1, dep2: Dependency2):
            super().__init__(host)
            self.dep1 = dep1
            self.dep2 = dep2

    class Dependency4(MultihostUtility):
        def __init__(self, host):
            super().__init__(host)

    class DependencyUtility(MultihostUtilityMock):
        def __init__(self, host, dep1, dep2, dep3, dep2_again, dep4, *args, **kwargs):
            super().__init__(host, *args, **kwargs)

    dep1 = Dependency1(mock_host)
    dep2 = Dependency2(mock_host)
    dep2_again = Dependency2(mock_host)
    dep3 = Dependency3(mock_host, dep1, dep2)
    dep4 = Dependency4(mock_host)

    util = DependencyUtility(mock_host, dep1, dep2, dep3, dep2_again, dep4)
    assert util._mh_utility_dependencies == {dep1, dep2, dep3, dep2_again, dep4}


def test_multihost__mh_utility_setup(mocker: MockerFixture, mock_host: MultihostHost):
    class Utility(MultihostUtilityMock):
        def setup(self):
            return super().setup()

        def use_me(self):
            pass

    # setup available
    mock = mocker.patch.object(Utility, "setup")
    util: MultihostUtility = Utility(mock_host)

    assert not util._op_state.check_success("setup")
    mh_utility_setup(util)
    mock.assert_called_once()
    assert util._op_state.check_success("setup")

    # setup not available
    class UtilityWithout(MultihostUtilityMock):
        pass

    mock = mocker.patch.object(UtilityWithout, "setup")
    util = UtilityWithout(mock_host)

    assert not util._op_state.check_success("setup")
    mh_utility_setup(util)
    mock.assert_not_called()
    assert util._op_state.check_success("setup")

    # postponed setup
    mock = mocker.patch.object(Utility, "setup")
    util = Utility(mock_host).postpone_setup()
    assert not util._op_state.check_success("setup")
    mh_utility_setup(util)
    mock.assert_not_called()
    assert not util._op_state.check_success("setup")
    util.use_me()
    mock.assert_called()
    assert util._op_state.check_success("setup")


def test_multihost__mh_utility_teardown(mocker: MockerFixture, mock_host: MultihostHost):
    class Utility(MultihostUtilityMock):
        def teardown(self):
            return super().teardown()

        def use_me(self):
            pass

    # teardown available
    mock = mocker.patch.object(Utility, "teardown")
    util: MultihostUtility = Utility(mock_host)

    mh_utility_setup(util)
    assert util._op_state.check_success("setup")
    mh_utility_teardown(util)
    mock.assert_called_once()

    # teardown not available
    class UtilityWithout(MultihostUtilityMock):
        pass

    mock = mocker.patch.object(UtilityWithout, "teardown")
    util = UtilityWithout(mock_host)

    mh_utility_setup(util)
    assert util._op_state.check_success("setup")
    mh_utility_teardown(util)
    mock.assert_not_called()

    # postponed setup
    mock_setup = mocker.patch.object(Utility, "setup")
    mock_teardown = mocker.patch.object(Utility, "teardown")
    util = Utility(mock_host).postpone_setup()
    assert not util._op_state.check_success("setup")
    mh_utility_setup(util)
    mock_setup.assert_not_called()
    assert not util._op_state.check_success("setup")
    mh_utility_teardown(util)
    mock_teardown.assert_not_called()
    util.use_me()
    assert util._op_state.check_success("setup")
    mh_utility_teardown(util)
    mock_teardown.assert_called_once()
