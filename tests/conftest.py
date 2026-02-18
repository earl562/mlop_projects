"""Shared test fixtures."""

from unittest.mock import patch

import mlflow
import pytest


@pytest.fixture(autouse=True)
def _disable_mlflow_tracing():
    """Disable MLflow tracing during tests — no side effects, no mlruns/ writes."""
    mlflow.tracing.disable()
    yield
    mlflow.tracing.enable()


@pytest.fixture(autouse=True)
def _clear_discovery_cache():
    """Clear discovery cache before each test and disable disk cache."""
    from plotlot.ingestion.discovery import clear_cache
    clear_cache()
    with patch("plotlot.ingestion.discovery._read_disk_cache", return_value=None), \
         patch("plotlot.ingestion.discovery._write_disk_cache"):
        yield
    clear_cache()
