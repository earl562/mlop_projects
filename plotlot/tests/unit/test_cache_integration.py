"""Tests for report cache integration in the SSE pipeline and cost dashboard.

Covers:
- Cache hit skips pipeline and returns cached data via SSE
- Cache miss runs the full pipeline and writes to cache
- Cache write failure does not break the pipeline
- Cost dashboard endpoint returns expected structure
"""

from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.core.types import (
    ConstraintResult,
    DensityAnalysis,
    NumericZoningParams,
    PropertyRecord,
    Setbacks,
    ZoningReport,
)


def _mock_report() -> ZoningReport:
    """Build a realistic mock ZoningReport for test assertions."""
    return ZoningReport(
        address="171 NE 209th Ter, Miami, FL 33179",
        formatted_address="171 NE 209th Ter, Miami Gardens, FL 33179",
        municipality="Miami Gardens",
        county="Miami-Dade",
        lat=25.957,
        lng=-80.199,
        zoning_district="R-1",
        zoning_description="Single-Family Residential",
        allowed_uses=["Single-family dwelling"],
        conditional_uses=["Home occupation"],
        prohibited_uses=[],
        setbacks=Setbacks(front="25 ft", side="7.5 ft", rear="25 ft"),
        max_height="35 ft / 2 stories",
        max_density="6 units per acre",
        floor_area_ratio="0.50",
        lot_coverage="40%",
        min_lot_size="7,500 sq ft",
        parking_requirements="2 spaces per dwelling unit",
        property_record=PropertyRecord(
            folio="3422120000010",
            address="171 NE 209TH TER",
            municipality="Miami Gardens",
            county="Miami-Dade",
            zoning_code="R-1",
            lot_size_sqft=7500.0,
            lot_dimensions="75 x 100",
            bedrooms=3,
            bathrooms=2.0,
            year_built=1965,
        ),
        numeric_params=NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=7500.0,
            setback_front_ft=25.0,
            setback_side_ft=7.5,
            setback_rear_ft=25.0,
            max_height_ft=35.0,
            max_stories=2,
        ),
        density_analysis=DensityAnalysis(
            max_units=1,
            governing_constraint="density",
            constraints=[
                ConstraintResult(
                    name="density",
                    max_units=1,
                    raw_value=1.033,
                    formula="7500 sqft * 6.0 units/acre / 43560 = 1.033",
                    is_governing=True,
                ),
            ],
            lot_size_sqft=7500.0,
            confidence="high",
        ),
        summary="Single-family residential property in Miami Gardens.",
        sources=["Sec. 34-342 -- R-1 Single-Family Residential"],
        confidence="high",
    )


def _mock_geo() -> dict:
    """Mock geocode result for Miami Gardens."""
    return {
        "municipality": "Miami Gardens",
        "county": "Miami-Dade",
        "lat": 25.957,
        "lng": -80.199,
        "accuracy": 1.0,
    }


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _reset_db_engine():
    """Reset the DB engine between tests to avoid event-loop-closed errors."""
    import plotlot.storage.db as db_mod

    db_mod._engine = None
    db_mod._session_factory = None
    yield
    db_mod._engine = None
    db_mod._session_factory = None


# ---------------------------------------------------------------------------
# Cache hit — SSE pipeline should be skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_skips_pipeline(client):
    """When cache returns a report, pipeline steps 2-5 are skipped."""
    report = _mock_report()
    cached_data = asdict(report)

    with (
        patch(
            "plotlot.api.routes.geocode_address",
            new_callable=AsyncMock,
            return_value=_mock_geo(),
        ),
        patch(
            "plotlot.api.routes.get_cached_report",
            new_callable=AsyncMock,
            return_value=cached_data,
        ),
        # These should NOT be called on a cache hit
        patch(
            "plotlot.api.routes.lookup_property",
            new_callable=AsyncMock,
        ) as mock_property,
        patch(
            "plotlot.api.routes.hybrid_search",
            new_callable=AsyncMock,
        ) as mock_search,
        patch(
            "plotlot.api.routes._agentic_analysis",
            new_callable=AsyncMock,
        ) as mock_analysis,
    ):
        resp = await client.post(
            "/api/v1/analyze/stream",
            json={"address": "171 NE 209th Ter, Miami, FL 33179"},
        )

    assert resp.status_code == 200
    body = resp.text

    # Verify cache_hit step was emitted
    assert "cache_hit" in body
    assert "Using cached analysis" in body

    # Verify the cached result was returned
    assert "R-1" in body

    # Verify pipeline steps were NOT called
    mock_property.assert_not_called()
    mock_search.assert_not_called()
    mock_analysis.assert_not_called()


# ---------------------------------------------------------------------------
# Cache miss — pipeline runs and caches result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_runs_pipeline_and_caches(client):
    """When cache returns None, pipeline runs normally and result is cached."""
    report = _mock_report()
    geo = _mock_geo()

    mock_session = AsyncMock()

    with (
        patch(
            "plotlot.api.routes.geocode_address",
            new_callable=AsyncMock,
            return_value=geo,
        ),
        patch(
            "plotlot.api.routes.get_cached_report",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "plotlot.api.routes.lookup_property",
            new_callable=AsyncMock,
            return_value=report.property_record,
        ),
        patch(
            "plotlot.api.routes.get_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ),
        patch(
            "plotlot.api.routes.hybrid_search",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "plotlot.api.routes._agentic_analysis",
            new_callable=AsyncMock,
            return_value=report,
        ),
        patch(
            "plotlot.api.routes.cache_report",
            new_callable=AsyncMock,
        ) as mock_cache_write,
        patch("plotlot.api.routes.start_run"),
        patch("plotlot.api.routes.log_params"),
        patch("plotlot.api.routes.log_metrics"),
        patch("plotlot.api.routes.set_tag"),
        patch("plotlot.api.routes.log_prompt_to_run"),
    ):
        resp = await client.post(
            "/api/v1/analyze/stream",
            json={"address": "171 NE 209th Ter, Miami, FL 33179"},
        )

    assert resp.status_code == 200
    body = resp.text

    # Pipeline should NOT report a cache hit
    assert "cache_hit" not in body

    # Result should still be returned
    assert "R-1" in body

    # Cache write should have been called with the address and report dict
    mock_cache_write.assert_awaited_once()
    call_args = mock_cache_write.call_args
    assert call_args[0][0] == "171 NE 209th Ter, Miami, FL 33179"


# ---------------------------------------------------------------------------
# Cache write failure — pipeline still completes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_write_failure_does_not_break_pipeline(client):
    """If cache_report raises, the pipeline result is still returned."""
    report = _mock_report()
    geo = _mock_geo()

    mock_session = AsyncMock()

    with (
        patch(
            "plotlot.api.routes.geocode_address",
            new_callable=AsyncMock,
            return_value=geo,
        ),
        patch(
            "plotlot.api.routes.get_cached_report",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "plotlot.api.routes.lookup_property",
            new_callable=AsyncMock,
            return_value=report.property_record,
        ),
        patch(
            "plotlot.api.routes.get_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ),
        patch(
            "plotlot.api.routes.hybrid_search",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "plotlot.api.routes._agentic_analysis",
            new_callable=AsyncMock,
            return_value=report,
        ),
        patch(
            "plotlot.api.routes.cache_report",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection lost"),
        ),
        patch("plotlot.api.routes.start_run"),
        patch("plotlot.api.routes.log_params"),
        patch("plotlot.api.routes.log_metrics"),
        patch("plotlot.api.routes.set_tag"),
        patch("plotlot.api.routes.log_prompt_to_run"),
    ):
        resp = await client.post(
            "/api/v1/analyze/stream",
            json={"address": "171 NE 209th Ter, Miami, FL 33179"},
        )

    assert resp.status_code == 200
    body = resp.text

    # The result should still be present despite cache write failure
    assert "R-1" in body
    assert "pipeline_error" not in body


# ---------------------------------------------------------------------------
# Cache lookup failure — pipeline continues normally
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_lookup_failure_continues_pipeline(client):
    """If get_cached_report raises, pipeline runs normally."""
    report = _mock_report()
    geo = _mock_geo()

    mock_session = AsyncMock()

    with (
        patch(
            "plotlot.api.routes.geocode_address",
            new_callable=AsyncMock,
            return_value=geo,
        ),
        patch(
            "plotlot.api.routes.get_cached_report",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ),
        patch(
            "plotlot.api.routes.lookup_property",
            new_callable=AsyncMock,
            return_value=report.property_record,
        ),
        patch(
            "plotlot.api.routes.get_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ),
        patch(
            "plotlot.api.routes.hybrid_search",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "plotlot.api.routes._agentic_analysis",
            new_callable=AsyncMock,
            return_value=report,
        ),
        patch(
            "plotlot.api.routes.cache_report",
            new_callable=AsyncMock,
        ),
        patch("plotlot.api.routes.start_run"),
        patch("plotlot.api.routes.log_params"),
        patch("plotlot.api.routes.log_metrics"),
        patch("plotlot.api.routes.set_tag"),
        patch("plotlot.api.routes.log_prompt_to_run"),
    ):
        resp = await client.post(
            "/api/v1/analyze/stream",
            json={"address": "171 NE 209th Ter, Miami, FL 33179"},
        )

    assert resp.status_code == 200
    body = resp.text

    # Pipeline should have run normally despite cache lookup failure
    assert "R-1" in body
    assert "pipeline_error" not in body


# ---------------------------------------------------------------------------
# Cost dashboard — E4
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_dashboard_returns_expected_structure(client):
    """GET /admin/costs returns aggregated cost data from MLflow."""
    # Build mock MLflow objects
    mock_run = MagicMock()
    mock_run.info.run_id = "run-abc-123"
    mock_run.info.start_time = 1709000000000
    mock_run.data.params = {"model": "meta/llama-3.3-70b-instruct"}
    mock_run.data.metrics = {
        "input_tokens": 1500.0,
        "output_tokens": 500.0,
        "total_tokens": 2000.0,
        "estimated_cost_usd": 0.0008,
    }

    mock_experiment = MagicMock()
    mock_experiment.experiment_id = "1"

    mock_client = MagicMock()
    mock_client.search_experiments.return_value = [mock_experiment]
    mock_client.search_runs.return_value = [mock_run]

    # Mock the MLflow module
    mock_mlflow = MagicMock()
    mock_mlflow.MlflowClient.return_value = mock_client

    with patch("plotlot.api.routes.set_tag"):  # prevent MLflow side effects
        with (
            patch("plotlot.observability.tracing._mlflow", mock_mlflow),
            patch("plotlot.observability.tracing.mlflow", mock_mlflow),
        ):
            # Patch at the import site in routes
            with patch("plotlot.api.routes.get_session", new_callable=AsyncMock):
                resp = await client.get("/api/v1/admin/costs")

    assert resp.status_code == 200
    data = resp.json()

    assert "total_estimated_cost_usd" in data
    assert "total_tokens" in data
    assert "query_count" in data
    assert "recent_queries" in data
    assert data["query_count"] == 1
    assert data["total_tokens"] == 2000
    assert data["total_estimated_cost_usd"] > 0

    query = data["recent_queries"][0]
    assert query["run_id"] == "run-abc-123"
    assert query["model"] == "meta/llama-3.3-70b-instruct"
    assert query["total_tokens"] == 2000


@pytest.mark.asyncio
async def test_cost_dashboard_no_mlflow(client):
    """GET /admin/costs returns graceful error when MLflow not installed."""
    with (
        patch("plotlot.observability.tracing.mlflow", None),
        patch("plotlot.observability.tracing._mlflow", None),
    ):
        resp = await client.get("/api/v1/admin/costs")

    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert "MLflow not installed" in data["error"]


@pytest.mark.asyncio
async def test_cost_dashboard_mlflow_error(client):
    """GET /admin/costs handles MLflow errors gracefully."""
    mock_mlflow = MagicMock()
    mock_mlflow.MlflowClient.side_effect = RuntimeError("connection refused")

    with (
        patch("plotlot.observability.tracing.mlflow", mock_mlflow),
        patch("plotlot.observability.tracing._mlflow", mock_mlflow),
    ):
        resp = await client.get("/api/v1/admin/costs")

    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert "RuntimeError" in data["error"]
