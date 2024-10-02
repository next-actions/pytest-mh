from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from pytest_mh.conn import Connection
from pytest_mh.conn.container import ContainerClient
from pytest_mh.conn.ssh import SSHClient


@pytest.fixture(autouse=True)
def disallow_connection(mocker: MockerFixture):
    """
    Raise RuntimeError if a test tries to connect to the remote host.
    """
    classes = [Connection, SSHClient, ContainerClient]
    for cls in classes:
        mocker.patch.object(
            cls,
            "connect",
            side_effect=RuntimeError(f"Test attempted to connect to remote host ({cls.__name__})"),
        )
