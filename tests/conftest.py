"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _clear_discovery_cache():
    """Clear discovery cache before each test to avoid cross-test pollution."""
    from plotlot.ingestion.discovery import clear_cache
    clear_cache()
    yield
    clear_cache()
