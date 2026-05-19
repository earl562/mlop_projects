"""Regression tests for startup/runtime degraded diagnostics."""

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.api.main import _runtime_health, app, lifespan


@pytest.mark.asyncio
async def test_lifespan_records_runtime_warnings_for_mlflow_and_db_failures():
    with (
        patch("plotlot.api.main.configure_mlflow", return_value=False),
        patch("plotlot.api.main.init_db", new=AsyncMock(side_effect=ConnectionError("refused"))),
    ):
        async with lifespan(app):
            assert _runtime_health["startup_mode"] == "degraded"
            assert "mlflow_unavailable" in _runtime_health["startup_warnings"]
            assert "database_unavailable" in _runtime_health["startup_warnings"]
