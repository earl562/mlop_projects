"""Unit tests for ingestion/acp_coordinator.py — ACP on-demand ingestion."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


from plotlot.core.errors import NoAdapterError
from plotlot.core.types import ChunkMetadata, TextChunk
from plotlot.ingestion.acp_coordinator import (
    IngestProgress,
    IngestRequest,
    run_on_demand_ingestion,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_chunk(municipality: str = "Fremont", idx: int = 0) -> TextChunk:
    return TextChunk(
        text="Section 12.3 — Residential density limit is 25 units per acre.",
        metadata=ChunkMetadata(
            municipality=municipality,
            county="Alameda",
            chapter="Chapter 12",
            section="12.3",
            section_title="Residential Density",
            zone_codes=["RM-25"],
            chunk_index=idx,
            municode_node_id=f"node_{idx:04d}",
        ),
    )


def _make_chunks(n: int = 3, municipality: str = "Fremont") -> list[TextChunk]:
    return [_make_chunk(municipality, i) for i in range(n)]


def _make_embedding(dim: int = 1024) -> list[float]:
    return [0.1] * dim


def _collect_stages(events: list[IngestProgress]) -> list[str]:
    return [e.stage for e in events]


async def _drain(gen) -> list[IngestProgress]:
    return [ev async for ev in gen]


# ── IngestRequest / IngestProgress models ─────────────────────────────────────


def test_ingest_request_defaults():
    req = IngestRequest(municipality="Fremont", state="ca")
    assert req.state == "ca"
    assert req.trigger == "search_miss"
    assert req.county is None


def test_ingest_request_full():
    req = IngestRequest(
        municipality="Oakland",
        state="CA",
        county="Alameda",
        trigger="manual",
    )
    assert req.county == "Alameda"
    assert req.trigger == "manual"


def test_ingest_progress_defaults():
    prog = IngestProgress(stage="fetching", message="Downloading…")
    assert prog.chunks_done == 0
    assert prog.chunks_total == 0
    assert prog.complete is False
    assert prog.error is None


def test_ingest_progress_complete():
    prog = IngestProgress(
        stage="complete",
        message="Done",
        chunks_done=42,
        chunks_total=42,
        complete=True,
    )
    assert prog.complete is True
    assert prog.error is None


def test_ingest_progress_error():
    prog = IngestProgress(
        stage="error",
        message="Something broke",
        error="fetch_error",
        complete=True,
    )
    assert prog.error == "fetch_error"
    assert prog.complete is True


def test_ingest_progress_model_dump():
    prog = IngestProgress(stage="storing", message="Saving…", chunks_done=10, chunks_total=50)
    d = prog.model_dump()
    assert d["stage"] == "storing"
    assert d["chunks_done"] == 10
    assert "error" in d


# ── run_on_demand_ingestion — NoAdapterError ──────────────────────────────────


async def test_no_adapter_yields_error_event():
    req = IngestRequest(municipality="Unknown City", state="ZZ")

    with patch(
        "plotlot.ingestion.acp_coordinator.resolve_adapter",
        AsyncMock(side_effect=NoAdapterError("Unknown City", "ZZ")),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    stages = _collect_stages(events)
    assert "resolving" in stages
    assert "error" in stages

    error_event = next(e for e in events if e.stage == "error")
    assert error_event.complete is True
    assert error_event.error == "no_adapter"


async def test_resolve_generic_exception_yields_error():
    req = IngestRequest(municipality="Fremont", state="CA")

    with patch(
        "plotlot.ingestion.acp_coordinator.resolve_adapter",
        AsyncMock(side_effect=RuntimeError("network timeout")),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    error_event = next(e for e in events if e.stage == "error")
    assert error_event.error == "resolve_error"
    assert "network timeout" in error_event.message


# ── run_on_demand_ingestion — fetch_chunks errors ─────────────────────────────


async def test_empty_chunks_yields_error():
    req = IngestRequest(municipality="Fremont", state="CA")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    mock_adapter.fetch_chunks = AsyncMock(return_value=[])

    with patch(
        "plotlot.ingestion.acp_coordinator.resolve_adapter",
        AsyncMock(return_value=mock_adapter),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    error_event = next(e for e in events if e.stage == "error")
    assert error_event.error == "empty_source"
    assert error_event.complete is True


async def test_fetch_exception_yields_error():
    req = IngestRequest(municipality="Fremont", state="CA")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    mock_adapter.fetch_chunks = AsyncMock(side_effect=RuntimeError("scrape failed"))

    with patch(
        "plotlot.ingestion.acp_coordinator.resolve_adapter",
        AsyncMock(return_value=mock_adapter),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    error_event = next(e for e in events if e.stage == "error")
    assert error_event.error == "fetch_error"


# ── run_on_demand_ingestion — embed errors ────────────────────────────────────


async def test_embed_exception_yields_error():
    req = IngestRequest(municipality="Fremont", state="CA")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    mock_adapter.fetch_chunks = AsyncMock(return_value=_make_chunks(2))

    with (
        patch(
            "plotlot.ingestion.acp_coordinator.resolve_adapter",
            AsyncMock(return_value=mock_adapter),
        ),
        patch(
            "plotlot.ingestion.acp_coordinator.embed_texts",
            AsyncMock(side_effect=RuntimeError("NVIDIA API down")),
        ),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    error_event = next(e for e in events if e.stage == "error")
    assert error_event.error == "embed_error"


async def test_all_chunks_filtered_yields_error():
    """validate_chunks filters everything → error event."""
    req = IngestRequest(municipality="Fremont", state="CA")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    mock_adapter.fetch_chunks = AsyncMock(return_value=_make_chunks(2))

    # Zero vectors → all fail validation
    zero_embs = [[0.0] * 1024, [0.0] * 1024]

    with (
        patch(
            "plotlot.ingestion.acp_coordinator.resolve_adapter",
            AsyncMock(return_value=mock_adapter),
        ),
        patch(
            "plotlot.ingestion.acp_coordinator.embed_texts",
            AsyncMock(return_value=zero_embs),
        ),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    error_event = next(e for e in events if e.stage == "error")
    assert error_event.error == "validation_error"


# ── run_on_demand_ingestion — store errors ────────────────────────────────────


async def test_store_exception_yields_error():
    req = IngestRequest(municipality="Fremont", state="CA")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    mock_adapter.fetch_chunks = AsyncMock(return_value=_make_chunks(2))

    good_embs = [_make_embedding() for _ in range(2)]

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=RuntimeError("DB write failed"))
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    with (
        patch(
            "plotlot.ingestion.acp_coordinator.resolve_adapter",
            AsyncMock(return_value=mock_adapter),
        ),
        patch(
            "plotlot.ingestion.acp_coordinator.embed_texts",
            AsyncMock(return_value=good_embs),
        ),
        patch("plotlot.ingestion.acp_coordinator.init_db", AsyncMock()),
        patch(
            "plotlot.ingestion.acp_coordinator.get_session",
            AsyncMock(return_value=mock_session),
        ),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    error_event = next(e for e in events if e.stage == "error")
    assert error_event.error == "store_error"


# ── run_on_demand_ingestion — happy path ──────────────────────────────────────


async def test_happy_path_all_stages_present():
    """Full successful run emits all stage events and a final complete."""
    req = IngestRequest(municipality="Fremont", state="CA", county="Alameda")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    mock_adapter.fetch_chunks = AsyncMock(return_value=_make_chunks(3))

    good_embs = [_make_embedding() for _ in range(3)]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    with (
        patch(
            "plotlot.ingestion.acp_coordinator.resolve_adapter",
            AsyncMock(return_value=mock_adapter),
        ),
        patch(
            "plotlot.ingestion.acp_coordinator.embed_texts",
            AsyncMock(return_value=good_embs),
        ),
        patch("plotlot.ingestion.acp_coordinator.init_db", AsyncMock()),
        patch(
            "plotlot.ingestion.acp_coordinator.get_session",
            AsyncMock(return_value=mock_session),
        ),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    stages = _collect_stages(events)
    assert "resolving" in stages
    assert "fetching" in stages
    assert "embedding" in stages
    assert "storing" in stages
    assert "complete" in stages

    # No error events
    assert not any(e.stage == "error" for e in events)

    # Final event is complete
    assert events[-1].stage == "complete"
    assert events[-1].complete is True


async def test_happy_path_complete_event_has_chunk_count():
    req = IngestRequest(municipality="Fremont", state="CA")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    n_chunks = 5
    mock_adapter.fetch_chunks = AsyncMock(return_value=_make_chunks(n_chunks))

    good_embs = [_make_embedding() for _ in range(n_chunks)]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    with (
        patch(
            "plotlot.ingestion.acp_coordinator.resolve_adapter",
            AsyncMock(return_value=mock_adapter),
        ),
        patch(
            "plotlot.ingestion.acp_coordinator.embed_texts",
            AsyncMock(return_value=good_embs),
        ),
        patch("plotlot.ingestion.acp_coordinator.init_db", AsyncMock()),
        patch(
            "plotlot.ingestion.acp_coordinator.get_session",
            AsyncMock(return_value=mock_session),
        ),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    complete = events[-1]
    assert complete.chunks_done == n_chunks
    assert complete.chunks_total == n_chunks


async def test_happy_path_municipality_name_normalised_in_logs(caplog):
    """Coordinator strips whitespace from municipality name."""
    req = IngestRequest(municipality="  Fremont  ", state="CA")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    mock_adapter.fetch_chunks = AsyncMock(return_value=_make_chunks(1))

    good_embs = [_make_embedding()]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    with (
        patch(
            "plotlot.ingestion.acp_coordinator.resolve_adapter",
            AsyncMock(return_value=mock_adapter),
        ),
        patch(
            "plotlot.ingestion.acp_coordinator.embed_texts",
            AsyncMock(return_value=good_embs),
        ),
        patch("plotlot.ingestion.acp_coordinator.init_db", AsyncMock()),
        patch(
            "plotlot.ingestion.acp_coordinator.get_session",
            AsyncMock(return_value=mock_session),
        ),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    assert events[-1].stage == "complete"


# ── State normalisation ───────────────────────────────────────────────────────


async def test_state_uppercased_before_adapter_call():
    """State is uppercased before resolve_adapter is called."""
    req = IngestRequest(municipality="Fremont", state="ca")

    captured = {}

    async def mock_resolve(muni, st, county=None):
        captured["state"] = st
        raise NoAdapterError(muni, st)

    with patch("plotlot.ingestion.acp_coordinator.resolve_adapter", mock_resolve):
        await _drain(run_on_demand_ingestion(req))

    assert captured["state"] == "CA"


# ── Progress event stream ordering ───────────────────────────────────────────


async def test_events_ordered_resolving_fetching_embedding_storing_complete():
    req = IngestRequest(municipality="Fremont", state="CA")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    mock_adapter.fetch_chunks = AsyncMock(return_value=_make_chunks(2))
    good_embs = [_make_embedding(), _make_embedding()]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    with (
        patch(
            "plotlot.ingestion.acp_coordinator.resolve_adapter",
            AsyncMock(return_value=mock_adapter),
        ),
        patch(
            "plotlot.ingestion.acp_coordinator.embed_texts",
            AsyncMock(return_value=good_embs),
        ),
        patch("plotlot.ingestion.acp_coordinator.init_db", AsyncMock()),
        patch(
            "plotlot.ingestion.acp_coordinator.get_session",
            AsyncMock(return_value=mock_session),
        ),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    # Verify stage ordering is monotonically correct
    stage_order = ["resolving", "fetching", "embedding", "storing", "complete"]
    seen_stages = [e.stage for e in events if e.stage in stage_order]
    last_seen_idx = -1
    for s in seen_stages:
        idx = stage_order.index(s)
        assert idx >= last_seen_idx, f"Stage {s!r} appeared out of order"
        last_seen_idx = idx


# ── Terminal event guarantees ─────────────────────────────────────────────────


async def test_last_event_always_has_complete_true_on_success():
    req = IngestRequest(municipality="Fremont", state="CA")
    mock_adapter = AsyncMock()
    mock_adapter.name = "municode"
    mock_adapter.fetch_chunks = AsyncMock(return_value=_make_chunks(1))
    good_embs = [_make_embedding()]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    with (
        patch(
            "plotlot.ingestion.acp_coordinator.resolve_adapter",
            AsyncMock(return_value=mock_adapter),
        ),
        patch("plotlot.ingestion.acp_coordinator.embed_texts", AsyncMock(return_value=good_embs)),
        patch("plotlot.ingestion.acp_coordinator.init_db", AsyncMock()),
        patch(
            "plotlot.ingestion.acp_coordinator.get_session",
            AsyncMock(return_value=mock_session),
        ),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    assert events[-1].complete is True


async def test_last_event_always_has_complete_true_on_error():
    req = IngestRequest(municipality="Unknown", state="ZZ")

    with patch(
        "plotlot.ingestion.acp_coordinator.resolve_adapter",
        AsyncMock(side_effect=NoAdapterError("Unknown", "ZZ")),
    ):
        events = await _drain(run_on_demand_ingestion(req))

    assert events[-1].complete is True


# ── model_dump() is SSE-safe ──────────────────────────────────────────────────


def test_ingest_progress_model_dump_is_json_serialisable():
    """model_dump() output must be JSON-serialisable for SSE transport."""
    import json

    prog = IngestProgress(
        stage="storing",
        message="Saving…",
        chunks_done=50,
        chunks_total=100,
    )
    payload = prog.model_dump()
    # Should not raise
    json.dumps(payload)


def test_ingest_request_model_dump_is_json_serialisable():
    import json

    req = IngestRequest(municipality="Oakland", state="CA", county="Alameda")
    json.dumps(req.model_dump())
