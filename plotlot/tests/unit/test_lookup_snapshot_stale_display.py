from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.core.lookup_snapshot import (
    DisplayState,
    EvidenceId,
    EvidenceSourceMetadata,
    FreshnessStatus,
    LookupSnapshot,
    LookupSnapshotId,
    RunId,
    SiteId,
)
from plotlot.core.types import PropertyRecord, ZoningReport
from plotlot.pipeline.lookup_snapshot_fields import zoning_field
from plotlot.pipeline.lookup_snapshot_store import build_stored_lookup_snapshot


def _snapshot_report() -> ZoningReport:
    return ZoningReport(
        address="7940 Plantation Blvd, Miramar, FL 33023",
        formatted_address="7940 Plantation Blvd, Miramar, FL 33023",
        municipality="Miramar",
        county="Broward",
        zoning_district="RS-4",
        max_height="35 ft",
        parking_requirements="2 spaces per unit",
        property_record=PropertyRecord(
            folio="504210230010",
            address="7940 PLANTATION BLVD",
            municipality="Miramar",
            county="Broward",
            zoning_code="RS-4",
            lot_size_sqft=8000.0,
        ),
        sources=("Sec. 500 - Dimensional Standards",),
        confidence="medium",
    )


def _stale_source_snapshot() -> LookupSnapshot:
    evidence_id = EvidenceId("ev_ordinance_stale")
    return LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId("ls_stale_source"),
        site_id=SiteId("site_stale_source"),
        run_id=RunId("run_stale_source"),
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
                source_url="https://example.gov/zoning-code",
                source_title="Zoning Code",
                effective_date="2020-01-01",
            ),
        ),
    )


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


def test_lookup_snapshot_evidence_records_surface_stale_source_metadata() -> None:
    # Given: a lookup snapshot cites an official ordinance source with stale metadata.
    snapshot = _stale_source_snapshot()

    # When: the snapshot is stored for evidence and trace replay.
    stored = build_stored_lookup_snapshot(snapshot)

    # Then: stale freshness is visible in evidence, display state, and trace outputs.
    record = stored.evidence_records[0]
    field = stored.snapshot.fields[0]
    assert record.quality_flags == ("stale_source",)
    assert record.warnings == ("stale_source",)
    assert field.display_state is DisplayState.STALE
    assert field.freshness is FreshnessStatus.STALE
    assert "stale_source" in field.warnings
    assert stored.trace_record.field_evidence[0].display_state == "stale"
    assert stored.trace_record.ingestion_quality_flags == ("stale_source",)


@pytest.mark.asyncio
async def test_lookup_snapshot_creation_returns_stale_display_state_for_stale_sources(
    transport: ASGITransport,
) -> None:
    from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store

    # Given: the lookup pipeline returns a snapshot backed by stale ordinance evidence.
    clear_lookup_snapshot_store()
    report = _snapshot_report()
    report.lookup_snapshot = _stale_source_snapshot()
    persist_snapshot = AsyncMock()

    # When: the lookup snapshot is created through the HTTP surface.
    with (
        patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock),
        patch(
            "plotlot.api.lookup_snapshot_creation.lookup_address",
            new_callable=AsyncMock,
            return_value=report,
        ),
        patch(
            "plotlot.api.lookup_snapshot_creation.persist_created_lookup_snapshot",
            persist_snapshot,
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/lookup-snapshots",
                json={"address": "7940 Plantation Blvd, Miramar, FL 33023"},
            )

    # Then: the API response and persisted snapshot expose stale, not verified, fields.
    assert created.status_code == 200
    body = created.json()
    fields = {field["key"]: field for field in body["fields"]}
    persisted_snapshot = persist_snapshot.await_args.args[0]
    assert fields["zoning.district"]["display_state"] == "stale"
    assert fields["zoning.district"]["freshness"] == "stale"
    assert "stale_source" in fields["zoning.district"]["warnings"]
    assert persisted_snapshot.fields[0].display_state is DisplayState.STALE
