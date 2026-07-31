"""Eval test fixtures — golden data loading and MLflow experiment setup."""

import json
import os
from pathlib import Path

import mlflow
import pytest

from .scorers import ALL_SCORERS

GOLDEN_DATA_PATH = Path(__file__).parent / "golden_data.json"
_MLFLOW_WORKER_ENV = {
    "MLFLOW_ASYNC_TRACE_LOGGING_MAX_WORKERS": "1",
    "MLFLOW_GENAI_EVAL_MAX_SCORER_WORKERS": "1",
    "MLFLOW_GENAI_EVAL_MAX_WORKERS": "1",
}


@pytest.fixture(scope="session")
def golden_data() -> list[dict]:
    """Load the golden evaluation dataset from JSON."""
    data = json.loads(GOLDEN_DATA_PATH.read_text())
    assert len(data) >= 2, f"Expected at least 2 golden samples, got {len(data)}"
    return data


@pytest.fixture(scope="session")
def all_scorers():
    """All deterministic scorers for evaluation."""
    return ALL_SCORERS


@pytest.fixture(scope="session")
def _eval_tracking_uri(tmp_path_factory):
    tracking_dir = tmp_path_factory.mktemp("mlflow_eval")
    return f"sqlite:///{tracking_dir}/mlflow.db"


@pytest.fixture(autouse=True)
def _enable_eval_tracking(_eval_tracking_uri):
    """Re-enable MLflow tracing for eval tests (root conftest disables it).

    Uses a temp directory for the tracking store so eval runs don't
    pollute the main mlruns/ during automated test runs.
    """
    prev_uri = mlflow.get_tracking_uri()
    prior_worker_env = {name: os.environ.get(name) for name in _MLFLOW_WORKER_ENV}
    os.environ.update(_MLFLOW_WORKER_ENV)
    mlflow.set_tracking_uri(_eval_tracking_uri)
    mlflow.set_experiment("plotlot-eval")
    mlflow.tracing.enable()

    yield

    while mlflow.active_run() is not None:
        mlflow.end_run()
    mlflow.flush_trace_async_logging(terminate=True)
    mlflow.tracing.disable()
    mlflow.set_tracking_uri(prev_uri)
    for name, value in prior_worker_env.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
