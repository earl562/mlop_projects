"""Eval test fixtures — golden data loading and MLflow experiment setup."""

import json
from pathlib import Path

import mlflow
import pytest

from .scorers import ALL_SCORERS

GOLDEN_DATA_PATH = Path(__file__).parent / "golden_data.json"


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


@pytest.fixture(autouse=True)
def _enable_eval_tracking(tmp_path_factory):
    """Re-enable MLflow tracing for eval tests (root conftest disables it).

    Uses a temp directory for the tracking store so eval runs don't
    pollute the main mlruns/ during automated test runs.
    """
    tracking_dir = tmp_path_factory.mktemp("mlflow_eval")
    tracking_uri = f"sqlite:///{tracking_dir}/mlflow.db"

    prev_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("plotlot-eval")
    mlflow.tracing.enable()

    yield

    mlflow.tracing.disable()
    mlflow.set_tracking_uri(prev_uri)
