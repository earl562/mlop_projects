from __future__ import annotations

from datetime import UTC, datetime

import pytest

from plotlot.core.lookup_snapshot import (
    EvidenceId,
    EvidenceSourceMetadata,
    LookupSnapshot,
    LookupSnapshotId,
    RunId,
    SiteId,
)
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_fields import zoning_field
from plotlot.pipeline.lookup_snapshot_repository import (
    DEFAULT_LOOKUP_PROJECT_ID,
    DEFAULT_LOOKUP_WORKSPACE_ID,
    LookupSnapshotPersistenceContext,
    load_lookup_snapshot_record,
    persist_lookup_snapshot,
)
from plotlot.storage.models import AnalysisRun, EvidenceItem, Project, Site, ToolRun, Workspace
from tests.unit.lookup_snapshot_repository_fixtures import FakePersistenceSession, report


@pytest.mark.asyncio
async def test_persist_lookup_snapshot_writes_harness_records_with_evidence_ids() -> None:
    # Given: a verified lookup snapshot and an empty harness persistence session.
    session = FakePersistenceSession()
    snapshot = build_lookup_snapshot(report())
    context = LookupSnapshotPersistenceContext(
        request_address="7940 Plantation Blvd, Miramar, FL 33023",
    )

    # When: the snapshot is persisted into the harness spine.
    stored = await persist_lookup_snapshot(session, snapshot, context)

    # Then: workspace, project, site, run, tool, and evidence records are durable.
    assert stored.trace_record.evidence_ids
    assert session.committed == 1
    assert await session.get(Workspace, DEFAULT_LOOKUP_WORKSPACE_ID) is not None
    assert await session.get(Project, DEFAULT_LOOKUP_PROJECT_ID) is not None
    assert await session.get(Site, str(snapshot.site_id)) is not None

    run = await session.get(AnalysisRun, str(snapshot.lookup_snapshot_id))
    assert run is not None
    assert run.status == "completed"
    assert run.output_json["lookup_snapshot"]["lookup_snapshot_id"] == str(
        snapshot.lookup_snapshot_id
    )
    assert run.output_json["trace_record"]["evidence_ids"]

    tool_runs = [row for row in session.added if isinstance(row, ToolRun)]
    assert len(tool_runs) == 1
    assert tool_runs[0].analysis_run_id == str(snapshot.lookup_snapshot_id)
    assert (
        tool_runs[0].output_json["evidence_ids"] == run.output_json["trace_record"]["evidence_ids"]
    )

    evidence_items = [row for row in session.added if isinstance(row, EvidenceItem)]
    assert evidence_items
    assert {row.id for row in evidence_items} == set(
        run.output_json["trace_record"]["evidence_ids"]
    )
    assert evidence_items[0].metadata_json["lookup_snapshot_id"] == str(snapshot.lookup_snapshot_id)


@pytest.mark.asyncio
async def test_persist_lookup_snapshot_records_source_metadata_quality() -> None:
    # Given: a lookup snapshot whose evidence has no captured source URL or effective date.
    session = FakePersistenceSession()
    snapshot = build_lookup_snapshot(report())

    # When: the snapshot is persisted into the harness spine.
    stored = await persist_lookup_snapshot(
        session,
        snapshot,
        LookupSnapshotPersistenceContext(request_address="7940 Plantation Blvd"),
    )

    # Then: evidence quality flags and scores are persisted for replayable review.
    first_record = stored.evidence_records[0]
    run = await session.get(AnalysisRun, str(snapshot.lookup_snapshot_id))
    evidence_items = [row for row in session.added if isinstance(row, EvidenceItem)]
    assert run is not None
    assert first_record.quality_flags == ("missing_source_url", "missing_effective_date")
    assert first_record.quality_score == 0.0
    assert run.output_json["evidence_records"][0]["quality_flags"] == [
        "missing_source_url",
        "missing_effective_date",
    ]
    trace_flags = run.output_json["trace_record"]["ingestion_quality_flags"]
    assert "missing_source_url" in trace_flags
    assert "missing_effective_date" in trace_flags
    assert evidence_items[0].metadata_json["quality_flags"] == [
        "missing_source_url",
        "missing_effective_date",
    ]
    assert evidence_items[0].value_json["quality_score"] == 0.0


@pytest.mark.asyncio
async def test_persist_lookup_snapshot_uses_ordinance_source_url_for_quality() -> None:
    # Given: a lookup snapshot backed by a captured authoritative ordinance URL.
    session = FakePersistenceSession()
    source_url = "https://library.municode.com/fl/miramar/codes/code_of_ordinances"
    snapshot = build_lookup_snapshot(report(source_urls=(source_url,)))

    # When: the snapshot is persisted into the harness spine.
    stored = await persist_lookup_snapshot(
        session,
        snapshot,
        LookupSnapshotPersistenceContext(request_address="7940 Plantation Blvd"),
    )

    # Then: ordinance evidence keeps the URL and is not flagged as missing source URL.
    ordinance_records = [
        record
        for record in stored.evidence_records
        if record.source_type == "authoritative_code_text"
    ]
    assert len(ordinance_records) == 1
    ordinance_record = ordinance_records[0]
    run = await session.get(AnalysisRun, str(snapshot.lookup_snapshot_id))
    evidence_items = [
        row
        for row in session.added
        if isinstance(row, EvidenceItem) and row.id == str(ordinance_record.evidence_id)
    ]
    assert run is not None
    assert evidence_items
    assert ordinance_record.source_url == source_url
    assert ordinance_record.source_title == "Dimensional Standards"
    assert ordinance_record.quality_flags == ("missing_effective_date",)
    assert ordinance_record.quality_score == 0.5
    trace_flags = run.output_json["trace_record"]["ingestion_quality_flags"]
    assert "missing_effective_date" in trace_flags
    assert evidence_items[0].metadata_json["source_url"] == source_url
    assert evidence_items[0].metadata_json["quality_flags"] == ["missing_effective_date"]


@pytest.mark.asyncio
async def test_persist_lookup_snapshot_preserves_explicit_source_metadata() -> None:
    # Given: a lookup snapshot has explicit official GIS source metadata.
    session = FakePersistenceSession()
    evidence_id = EvidenceId("ev_custom_zoning_layer")
    snapshot = LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId("ls_explicit_source_metadata"),
        site_id=SiteId("site_explicit_source_metadata"),
        run_id=RunId("run_explicit_source_metadata"),
        fields=(
            zoning_field(
                "zoning.district",
                "Zoning district",
                "RS-4",
                "",
                (evidence_id,),
            ),
        ),
        calculations=(),
        warnings=(),
        source_metadata=(
            EvidenceSourceMetadata(
                evidence_id=evidence_id,
                source_url="https://example.gov/arcgis/rest/services/Zoning/MapServer/0",
                source_title="Official Zoning Layer",
                source_type="authoritative_public_record",
                source_authority="official_gis",
                publisher="City GIS Department",
                retrieved_at="2026-06-21T10:15:00+00:00",
                effective_date="2026-01-15",
                parser_version="arcgis_feature.v2",
                schema_version="zoning_layer.v4",
                raw_artifact_ref="sha256:raw-zoning-feature",
                query_parameters=("f=json", "where=1=1"),
            ),
        ),
    )

    # When: the snapshot is persisted into the harness spine.
    stored = await persist_lookup_snapshot(
        session,
        snapshot,
        LookupSnapshotPersistenceContext(request_address="7940 Plantation Blvd"),
    )

    # Then: durable evidence keeps source authority instead of inferring from the ID.
    record = stored.evidence_records[0]
    evidence_items = [row for row in session.added if isinstance(row, EvidenceItem)]
    assert record.source_type == "authoritative_public_record"
    assert record.source_authority == "official_gis"
    assert record.publisher == "City GIS Department"
    assert record.retrieved_at == "2026-06-21T10:15:00+00:00"
    assert record.effective_date == "2026-01-15"
    assert record.parser_version == "arcgis_feature.v2"
    assert record.schema_version == "zoning_layer.v4"
    assert record.raw_artifact_ref == "sha256:raw-zoning-feature"
    assert record.query_parameters == ("f=json", "where=1=1")
    assert record.quality_flags == ()
    assert evidence_items[0].metadata_json["source_authority"] == "official_gis"
    assert evidence_items[0].metadata_json["publisher"] == "City GIS Department"
    assert evidence_items[0].metadata_json["query_parameters"] == ["f=json", "where=1=1"]


@pytest.mark.asyncio
async def test_persist_lookup_snapshot_records_quality_flags_in_trace() -> None:
    # Given: a lookup snapshot with zoning facts blocked by missing ordinance evidence.
    session = FakePersistenceSession()
    snapshot = build_lookup_snapshot(report(with_ordinance=False))

    # When: the snapshot is persisted into the harness spine.
    stored = await persist_lookup_snapshot(
        session,
        snapshot,
        LookupSnapshotPersistenceContext(request_address="7940 Plantation Blvd"),
    )

    # Then: the durable trace keeps the ingestion-quality flags needed for replay and evals.
    run = await session.get(AnalysisRun, str(snapshot.lookup_snapshot_id))
    assert run is not None
    assert "missing_evidence" in stored.trace_record.ingestion_quality_flags
    assert "missing_evidence" in run.output_json["trace_record"]["ingestion_quality_flags"]


@pytest.mark.asyncio
async def test_load_lookup_snapshot_record_reads_analysis_run_payload() -> None:
    # Given: a completed analysis run containing a recorded lookup snapshot payload.
    session = FakePersistenceSession()
    now = datetime.now(UTC)
    snapshot = build_lookup_snapshot(report())
    persisted = await persist_lookup_snapshot(
        session,
        snapshot,
        LookupSnapshotPersistenceContext(request_address="7940 Plantation Blvd"),
    )
    analysis_run = await session.get(AnalysisRun, str(snapshot.lookup_snapshot_id))
    assert analysis_run is not None
    analysis_run.completed_at = now

    # When: the durable snapshot record is loaded by snapshot ID.
    loaded = await load_lookup_snapshot_record(session, str(snapshot.lookup_snapshot_id))

    # Then: the API-ready snapshot, evidence, and trace payloads are recovered.
    assert loaded is not None
    assert loaded.snapshot_json["lookup_snapshot_id"] == str(snapshot.lookup_snapshot_id)
    assert loaded.evidence_records == tuple(
        record for record in analysis_run.output_json["evidence_records"]
    )
    assert loaded.trace_record == analysis_run.output_json["trace_record"]
    assert loaded.trace_record["run_id"] == persisted.trace_record.run_id
