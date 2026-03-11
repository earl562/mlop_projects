"""Unit tests for the in-memory analytics module and admin endpoints.

Covers:
- record_request increments counts correctly
- Latency percentile calculations (p50/p95/p99)
- Error rate calculation
- reset() clears all state
- GET /admin/analytics endpoint returns expected structure
- GET /admin/data-quality endpoint returns expected structure (DB mocked)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.analytics import get_analytics, record_request, reset


@pytest.fixture(autouse=True)
def _reset_analytics():
    """Reset analytics counters before and after each test."""
    reset()
    yield
    reset()


# ---------------------------------------------------------------------------
# Analytics module unit tests
# ---------------------------------------------------------------------------


class TestRecordRequest:
    def test_increments_count(self):
        """Recording a request increments the endpoint counter."""
        record_request("/api/v1/analyze", latency_ms=100.0)
        record_request("/api/v1/analyze", latency_ms=200.0)
        stats = get_analytics()
        assert stats["total_requests"] == 2
        assert stats["endpoints"]["/api/v1/analyze"]["count"] == 2

    def test_tracks_errors(self):
        """Error requests are counted separately."""
        record_request("/api/v1/analyze", latency_ms=100.0)
        record_request("/api/v1/analyze", latency_ms=500.0, is_error=True)
        stats = get_analytics()
        ep = stats["endpoints"]["/api/v1/analyze"]
        assert ep["count"] == 2
        assert ep["errors"] == 1

    def test_multiple_endpoints(self):
        """Stats are tracked independently per endpoint."""
        record_request("/api/v1/analyze", latency_ms=50.0)
        record_request("/api/v1/chat", latency_ms=75.0)
        record_request("/api/v1/chat", latency_ms=80.0)
        stats = get_analytics()
        assert stats["total_requests"] == 3
        assert stats["endpoints"]["/api/v1/analyze"]["count"] == 1
        assert stats["endpoints"]["/api/v1/chat"]["count"] == 2


class TestLatencyPercentiles:
    def test_single_request_percentiles(self):
        """With one request, all percentiles equal that value."""
        record_request("/test", latency_ms=42.0)
        ep = get_analytics()["endpoints"]["/test"]
        assert ep["latency_p50_ms"] == 42.0
        assert ep["latency_p95_ms"] == 42.0
        assert ep["latency_p99_ms"] == 42.0

    def test_many_requests_percentiles(self):
        """Percentiles are computed correctly over a range of latencies."""
        # Record latencies 1..100
        for i in range(1, 101):
            record_request("/test", latency_ms=float(i))
        ep = get_analytics()["endpoints"]["/test"]
        # p50 should be around the median
        assert 45 <= ep["latency_p50_ms"] <= 55
        # p95 should be around 95
        assert 90 <= ep["latency_p95_ms"] <= 100
        # p99 should be around 99
        assert 95 <= ep["latency_p99_ms"] <= 100

    def test_no_requests_zero_percentiles(self):
        """With no requests recorded, get_analytics returns empty endpoints."""
        stats = get_analytics()
        assert stats["endpoints"] == {}


class TestErrorRate:
    def test_error_rate_calculation(self):
        """Error rate is computed as errors/total * 100."""
        for _ in range(8):
            record_request("/test", latency_ms=10.0)
        for _ in range(2):
            record_request("/test", latency_ms=10.0, is_error=True)
        ep = get_analytics()["endpoints"]["/test"]
        assert ep["error_rate"] == 20.0

    def test_zero_errors(self):
        """Error rate is 0 when there are no errors."""
        record_request("/test", latency_ms=10.0)
        ep = get_analytics()["endpoints"]["/test"]
        assert ep["error_rate"] == 0


class TestReset:
    def test_reset_clears_all_data(self):
        """reset() clears all endpoint stats."""
        record_request("/a", latency_ms=10.0)
        record_request("/b", latency_ms=20.0, is_error=True)
        reset()
        stats = get_analytics()
        assert stats["total_requests"] == 0
        assert stats["total_errors"] == 0
        assert stats["endpoints"] == {}

    def test_reset_resets_uptime(self):
        """reset() resets the uptime counter."""
        stats_before = get_analytics()
        reset()
        stats_after = get_analytics()
        assert stats_after["uptime_seconds"] <= stats_before["uptime_seconds"]


class TestAnalyticsStructure:
    def test_analytics_has_expected_keys(self):
        """Analytics response contains all expected top-level keys."""
        stats = get_analytics()
        assert "uptime_seconds" in stats
        assert "total_requests" in stats
        assert "total_errors" in stats
        assert "endpoints" in stats

    def test_endpoint_entry_has_expected_keys(self):
        """Each endpoint entry has count, errors, error_rate, and percentiles."""
        record_request("/test", latency_ms=10.0)
        ep = get_analytics()["endpoints"]["/test"]
        expected_keys = {
            "count",
            "errors",
            "error_rate",
            "latency_p50_ms",
            "latency_p95_ms",
            "latency_p99_ms",
        }
        assert set(ep.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Admin endpoint integration tests (ASGI transport, DB mocked)
# ---------------------------------------------------------------------------


@pytest.fixture
def transport():
    from plotlot.api.main import app

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


@pytest.mark.asyncio
async def test_analytics_endpoint(client):
    """GET /admin/analytics returns expected structure."""
    # Seed some data first
    record_request("/api/v1/analyze", latency_ms=150.0)
    record_request("/api/v1/chat", latency_ms=80.0, is_error=True)

    resp = await client.get("/api/v1/admin/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_requests"] == 2
    assert data["total_errors"] == 1
    assert "/api/v1/analyze" in data["endpoints"]
    assert "/api/v1/chat" in data["endpoints"]
    assert data["endpoints"]["/api/v1/chat"]["errors"] == 1


@pytest.mark.asyncio
async def test_data_quality_endpoint(client):
    """GET /admin/data-quality returns per-municipality stats (DB mocked)."""
    from datetime import datetime, timezone

    mock_rows = [
        (
            "Miami Gardens",  # municipality
            "Miami-Dade",  # county
            3561,  # chunk_count
            42,  # section_count
            datetime(2025, 1, 1, tzinfo=timezone.utc),  # first_ingested
            datetime(2025, 6, 15, tzinfo=timezone.utc),  # last_ingested
            850,  # avg_chunk_length
            120,  # min_chunk_length
            4200,  # max_chunk_length
        ),
        (
            "Fort Lauderdale",
            "Broward",
            136,
            8,
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            920,
            200,
            3800,
        ),
    ]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = mock_rows
    mock_session.execute.return_value = mock_result

    with patch("plotlot.api.routes.get_session", return_value=mock_session):
        resp = await client.get("/api/v1/admin/data-quality")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_municipalities"] == 2
    assert data["total_chunks"] == 3561 + 136
    assert len(data["municipalities"]) == 2

    mg = data["municipalities"][0]
    assert mg["municipality"] == "Miami Gardens"
    assert mg["county"] == "Miami-Dade"
    assert mg["chunk_count"] == 3561
    assert mg["section_count"] == 42
    assert mg["first_ingested"] == "2025-01-01T00:00:00+00:00"
    assert mg["avg_chunk_length"] == 850

    fl = data["municipalities"][1]
    assert fl["municipality"] == "Fort Lauderdale"
    assert fl["chunk_count"] == 136


@pytest.mark.asyncio
async def test_data_quality_endpoint_handles_db_error(client):
    """GET /admin/data-quality gracefully handles DB errors."""
    mock_session = AsyncMock()
    mock_session.execute.side_effect = ConnectionError("Database unreachable")

    with patch("plotlot.api.routes.get_session", return_value=mock_session):
        resp = await client.get("/api/v1/admin/data-quality")

    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert data["municipalities"] == []
