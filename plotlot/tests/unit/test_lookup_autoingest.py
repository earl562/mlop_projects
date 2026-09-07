"""Tests for self-healing coverage in the analysis pipeline.

When the zoning ordinance search returns 0 chunks for a municipality, the
pipeline auto-triggers ACP on-demand ingestion and re-searches. This makes the
MCP/ACP path work for any municipality reachable by a source adapter — not just
pre-ingested ones — and degrades honestly when ingestion is not possible.

Regression context: the MCP run_full_analysis path (lookup_address) previously
never invoked ACP, so un-ingested cities (e.g. Las Vegas) returned no ordinance
text and the agent hallucinated a "could not be retrieved" message.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import plotlot.pipeline.lookup as lookup
from plotlot.ingestion.acp_coordinator import IngestProgress
from plotlot.pipeline.lookup import _gather_ordinance_sections


def _chunk() -> MagicMock:
    c = MagicMock()
    c.section = "19.06"
    c.section_title = "Residential Districts"
    c.chunk_text = "RS20 requires a minimum lot of 20,000 sqft."
    c.zone_codes = ["RS20"]
    c.score = 0.9
    return c


@pytest.fixture(autouse=True)
def _clear_attempts():
    """Reset the module-level auto-ingest guard between tests."""
    lookup._autoingest_attempts.clear()
    yield
    lookup._autoingest_attempts.clear()


@pytest.mark.asyncio
async def test_indexed_hit_does_not_trigger_ingestion() -> None:
    """When data is already indexed, ingestion must NOT run."""
    fake_session = AsyncMock()
    fake_session.close = AsyncMock()

    with (
        patch("plotlot.pipeline.lookup.get_session", AsyncMock(return_value=fake_session)),
        patch("plotlot.pipeline.lookup.hybrid_search", AsyncMock(return_value=[_chunk()])),
        patch("plotlot.ingestion.acp_coordinator.run_on_demand_ingestion") as mock_ingest,
    ):
        results, status = await _gather_ordinance_sections("San Jose", "CA", "Santa Clara", "RS20")

    assert status == "indexed"
    assert len(results) == 1
    mock_ingest.assert_not_called()


@pytest.mark.asyncio
async def test_miss_triggers_ingestion_then_research_succeeds() -> None:
    """0 results → ingest → re-search returns chunks → status 'auto_ingested'."""
    fake_session = AsyncMock()
    fake_session.close = AsyncMock()

    # First search empty, second (post-ingest) search returns a chunk.
    search_mock = AsyncMock(side_effect=[[], [_chunk()]])

    async def _fake_ingest(req):
        yield IngestProgress(stage="resolving", message="Finding source…")
        yield IngestProgress(stage="complete", message="Done", chunks_done=42, complete=True)

    with (
        patch("plotlot.pipeline.lookup.get_session", AsyncMock(return_value=fake_session)),
        patch("plotlot.pipeline.lookup.hybrid_search", search_mock),
        patch("plotlot.ingestion.acp_coordinator.run_on_demand_ingestion", _fake_ingest),
    ):
        results, status = await _gather_ordinance_sections("Fremont", "CA", "Alameda", "RM-25")

    assert status == "auto_ingested"
    assert len(results) == 1
    assert search_mock.call_count == 2


@pytest.mark.asyncio
async def test_ingestion_error_degrades_to_ingest_empty() -> None:
    """When ingestion errors (no adapter), status is 'ingest_empty' and no crash."""
    fake_session = AsyncMock()
    fake_session.close = AsyncMock()

    async def _failing_ingest(req):
        yield IngestProgress(
            stage="error", message="No adapter found", error="no_adapter", complete=True
        )

    with (
        patch("plotlot.pipeline.lookup.get_session", AsyncMock(return_value=fake_session)),
        patch("plotlot.pipeline.lookup.hybrid_search", AsyncMock(return_value=[])),
        patch("plotlot.ingestion.acp_coordinator.run_on_demand_ingestion", _failing_ingest),
    ):
        results, status = await _gather_ordinance_sections("Las Vegas", "NV", "Clark", "RS20")

    assert status == "ingest_empty"
    assert results == []


@pytest.mark.asyncio
async def test_missing_municipality_is_uncovered() -> None:
    """No municipality/state → 'uncovered', ingestion never attempted."""
    fake_session = AsyncMock()
    fake_session.close = AsyncMock()

    with (
        patch("plotlot.pipeline.lookup.get_session", AsyncMock(return_value=fake_session)),
        patch("plotlot.pipeline.lookup.hybrid_search", AsyncMock(return_value=[])),
        patch("plotlot.ingestion.acp_coordinator.run_on_demand_ingestion") as mock_ingest,
    ):
        results, status = await _gather_ordinance_sections("", "", "", "RS20")

    assert status == "uncovered"
    mock_ingest.assert_not_called()


@pytest.mark.asyncio
async def test_ttl_guard_prevents_repeat_ingestion() -> None:
    """Second attempt for the same place within the TTL window skips ingestion."""
    fake_session = AsyncMock()
    fake_session.close = AsyncMock()

    ingest_calls = {"n": 0}

    async def _empty_ingest(req):
        ingest_calls["n"] += 1
        yield IngestProgress(
            stage="error", message="empty source", error="empty_source", complete=True
        )

    with (
        patch("plotlot.pipeline.lookup.get_session", AsyncMock(return_value=fake_session)),
        patch("plotlot.pipeline.lookup.hybrid_search", AsyncMock(return_value=[])),
        patch("plotlot.ingestion.acp_coordinator.run_on_demand_ingestion", _empty_ingest),
    ):
        _, status1 = await _gather_ordinance_sections("Las Vegas", "NV", "Clark", "RS20")
        _, status2 = await _gather_ordinance_sections("Las Vegas", "NV", "Clark", "RS20")

    assert status1 == "ingest_empty"
    assert status2 == "ingest_empty"
    assert ingest_calls["n"] == 1  # second call short-circuited by the TTL guard
