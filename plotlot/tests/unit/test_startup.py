"""Regression tests for PlotLot application startup behavior."""

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.api.main import app, lifespan


@pytest.mark.asyncio
async def test_lifespan_continues_when_mlflow_and_db_init_fail():
    """The API should still boot in degraded mode when tracing or DB init fails."""
    otel_patch = patch("plotlot.api.main.configure_otel", return_value=True)
    mlflow_patch = patch("plotlot.api.main.configure_mlflow", return_value=False)
    init_db_patch = patch(
        "plotlot.api.main.init_db",
        new=AsyncMock(side_effect=ConnectionError("refused")),
    )
    with otel_patch as mock_otel, mlflow_patch as mock_mlflow, init_db_patch as mock_init_db:
        async with lifespan(app):
            pass

    mock_otel.assert_called_once()
    mock_mlflow.assert_called_once()
    mock_init_db.assert_awaited_once()
