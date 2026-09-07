"""Shared test fixtures."""

import ipaddress
import os
from pathlib import Path
import socket
import tempfile
from typing import TypeAlias, assert_never
from unittest.mock import patch

import mlflow
import pytest


_MLFLOW_TEST_DIR = Path(tempfile.gettempdir()) / "plotlot-mlflow-tests"
_MLFLOW_TEST_DIR.mkdir(parents=True, exist_ok=True)
SocketAddress: TypeAlias = str | bytes | tuple[str, int] | tuple[str, int, int, int]


class ExternalNetworkAccessError(RuntimeError):
    def __init__(self, host: str) -> None:
        self.host = host
        super().__init__(f"External network access blocked in tests: {host}")


def _ensure_local_address(address: SocketAddress) -> None:
    match address:
        case str() | bytes():
            return
        case (str(host), int()):
            normalized_host = host.split("%", maxsplit=1)[0]
        case (str(host), int(), int(), int()):
            normalized_host = host.split("%", maxsplit=1)[0]
        case unreachable:
            assert_never(unreachable)

    if normalized_host.casefold() == "localhost":
        return
    try:
        is_loopback = ipaddress.ip_address(normalized_host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise ExternalNetworkAccessError(normalized_host)


@pytest.fixture(autouse=True)
def _block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def local_connect(client: socket.socket, address: SocketAddress) -> None:
        _ensure_local_address(address)
        original_connect(client, address)

    def local_connect_ex(client: socket.socket, address: SocketAddress) -> int:
        _ensure_local_address(address)
        return original_connect_ex(client, address)

    monkeypatch.setattr(socket.socket, "connect", local_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", local_connect_ex)


@pytest.fixture(scope="session", autouse=True)
def _disable_mlflow_tracing():
    previous_tracking_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(_MLFLOW_TEST_DIR.as_uri())
    mlflow.tracing.disable()
    # MLflow file-store is in maintenance mode in current versions; enable() in
    # teardown raises MlflowTracingException unless this opt-in is set. The fixture
    # is self-contained so the gate is green regardless of shell env. (slice 0.2)
    _prior_allow = os.environ.get("MLFLOW_ALLOW_FILE_STORE")
    os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
    yield
    while mlflow.active_run() is not None:
        mlflow.end_run()
    mlflow.flush_trace_async_logging(terminate=True)
    mlflow.tracing.disable()
    mlflow.tracing.enable()
    mlflow.set_tracking_uri(previous_tracking_uri)
    if _prior_allow is None:
        os.environ.pop("MLFLOW_ALLOW_FILE_STORE", None)
    else:
        os.environ["MLFLOW_ALLOW_FILE_STORE"] = _prior_allow


@pytest.fixture(autouse=True)
def _clear_discovery_cache():
    """Clear discovery cache before each test and disable disk cache."""
    from plotlot.ingestion.discovery import clear_cache

    clear_cache()
    with (
        patch("plotlot.ingestion.discovery._read_disk_cache", return_value=None),
        patch("plotlot.ingestion.discovery._write_disk_cache"),
    ):
        yield
    clear_cache()
