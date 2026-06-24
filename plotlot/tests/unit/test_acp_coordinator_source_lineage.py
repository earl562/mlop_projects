from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from plotlot.core.types import ChunkMetadata, TextChunk
from plotlot.ingestion.acp_coordinator import IngestRequest, run_on_demand_ingestion
from plotlot.ingestion.acp_store_rows import OrdinanceChunkValue
from plotlot.ingestion.adapters.base import SourceAdapter
from plotlot.ingestion.adapters.result import IngestionAdapterResult, IngestionSourceRecord
from plotlot.storage.models import EvidenceItem


def _chunk() -> TextChunk:
    return TextChunk(
        text="Section 12.3 - Residential density limit is 25 units per acre.",
        metadata=ChunkMetadata(
            municipality="Fremont",
            county="Alameda",
            chapter="Chapter 12",
            section="12.3",
            section_title="Residential Density",
            zone_codes=["RM-25"],
            chunk_index=0,
            municode_node_id="html_1",
        ),
    )


def _source_record(url: str, index: int) -> IngestionSourceRecord:
    return IngestionSourceRecord(
        source_type="official_web_text",
        source_authority="municipal_web_page",
        source_url=url,
        source_title="Fremont zoning",
        publisher="Fremont",
        retrieved_at="2026-01-02T03:04:05+00:00",
        effective_date="",
        parser_version="html.v1",
        schema_version="ingestion_adapter_result.v1",
        query_parameters=(("urlIndex", str(index)),),
        raw_artifact_ref=url,
        lineage=("source", "raw_artifact", "parsed_chunks"),
        confidence=1.0,
        quality_score=0.5,
        quality_flags=("missing_effective_date",),
        warnings=("missing_effective_date",),
    )


class _ResultAdapter(SourceAdapter):
    name = "html"

    def __init__(self, result: IngestionAdapterResult) -> None:
        super().__init__("Fremont", "Alameda", "CA")
        self.result = result
        self.fetch_chunks_called = False

    async def fetch_chunks(self) -> list[TextChunk]:
        self.fetch_chunks_called = True
        return []

    async def fetch_ingestion_result(self) -> IngestionAdapterResult:
        return self.result


class _Excluded:
    def __getattr__(self, name: str) -> str:
        return f"excluded.{name}"


class _FakeInsert:
    excluded = _Excluded()

    def __init__(self, captured_values: list[OrdinanceChunkValue]) -> None:
        self.captured_values = captured_values

    def values(self, row_values: list[OrdinanceChunkValue]) -> _FakeInsert:
        self.captured_values.extend(row_values)
        return self

    def on_conflict_do_update(
        self, *, index_elements: list[str], set_: dict[str, str]
    ) -> _FakeInsert:
        return self


async def _drain(request: IngestRequest):
    return [event async for event in run_on_demand_ingestion(request)]


async def test_on_demand_ingestion_persists_adapter_source_url_for_matching_chunk() -> None:
    # Given: an adapter result with two source records and one chunk from the second URL.
    result = IngestionAdapterResult(
        adapter_name="html",
        municipality="Fremont",
        county="Alameda",
        state="CA",
        chunks=(_chunk(),),
        source_records=(
            _source_record("https://fremont.gov/zoning-a", 0),
            _source_record("https://fremont.gov/zoning-b", 1),
        ),
        quality_score=0.5,
        quality_flags=("missing_effective_date",),
        retrieved_at="2026-01-02T03:04:05+00:00",
        parser_version="html.v1",
        schema_version="ingestion_adapter_result.v1",
    )
    adapter = _ResultAdapter(result)
    captured_values: list[OrdinanceChunkValue] = []
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()

    # When: the coordinator runs through its real progress generator and store path.
    with (
        patch("plotlot.ingestion.acp_coordinator.resolve_adapter", AsyncMock(return_value=adapter)),
        patch(
            "plotlot.ingestion.acp_coordinator.embed_texts",
            AsyncMock(return_value=[[0.1] * 1024]),
        ),
        patch("plotlot.ingestion.acp_store.init_db", AsyncMock()),
        patch("plotlot.ingestion.acp_store.get_session", AsyncMock(return_value=session)),
        patch(
            "plotlot.ingestion.acp_store.pg_insert",
            lambda _model: _FakeInsert(captured_values),
        ),
    ):
        events = await _drain(IngestRequest(municipality="Fremont", state="CA", county="Alameda"))

    # Then: the inserted chunk keeps the matching adapter source URL and retrieval timestamp.
    assert events[-1].stage == "complete"
    assert adapter.fetch_chunks_called is False
    assert captured_values[0]["source_url"] == "https://fremont.gov/zoning-b"
    assert captured_values[0]["scraped_at"] == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


async def test_on_demand_ingestion_persists_source_record_as_evidence_when_context_exists() -> None:
    # Given: an adapter result with a durable workspace/project context.
    result = IngestionAdapterResult(
        adapter_name="html",
        municipality="Fremont",
        county="Alameda",
        state="CA",
        chunks=(_chunk(),),
        source_records=(_source_record("https://fremont.gov/zoning-b", 1),),
        quality_score=0.5,
        quality_flags=("missing_effective_date",),
        retrieved_at="2026-01-02T03:04:05+00:00",
        parser_version="html.v1",
        schema_version="ingestion_adapter_result.v1",
    )
    adapter = _ResultAdapter(result)
    captured_values: list[OrdinanceChunkValue] = []
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=None)

    # When: the coordinator stores chunks for an ingestion request with evidence context.
    with (
        patch("plotlot.ingestion.acp_coordinator.resolve_adapter", AsyncMock(return_value=adapter)),
        patch(
            "plotlot.ingestion.acp_coordinator.embed_texts",
            AsyncMock(return_value=[[0.1] * 1024]),
        ),
        patch("plotlot.ingestion.acp_store.init_db", AsyncMock()),
        patch("plotlot.ingestion.acp_store.get_session", AsyncMock(return_value=session)),
        patch(
            "plotlot.ingestion.acp_store.pg_insert",
            lambda _model: _FakeInsert(captured_values),
        ),
    ):
        events = await _drain(
            IngestRequest(
                municipality="Fremont",
                state="CA",
                county="Alameda",
                workspace_id="workspace_1",
                project_id="project_1",
                site_id="site_1",
            )
        )

    # Then: the adapter source record is persisted as evidence with quality metadata.
    evidence_row = session.add.call_args.args[0]
    assert events[-1].stage == "complete"
    assert events[-1].evidence_ids == (evidence_row.id,)
    assert events[-1].quality_flags == ("missing_effective_date",)
    assert events[-1].source_record_count == 1
    assert isinstance(evidence_row, EvidenceItem)
    assert evidence_row.workspace_id == "workspace_1"
    assert evidence_row.project_id == "project_1"
    assert evidence_row.site_id == "site_1"
    assert evidence_row.source_url == "https://fremont.gov/zoning-b"
    assert evidence_row.retrieval_method == "ingestion_adapter"
    assert evidence_row.metadata_json["quality_flags"] == ["missing_effective_date"]
