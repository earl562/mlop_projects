from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from plotlot.api.main import app
from plotlot.core.types import PropertyRecord, SourceRef, ZoningReport
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_repository import PersistedLookupSnapshotRecord
from plotlot.pipeline.lookup_snapshot_serialization import lookup_snapshot_to_dict
from plotlot.pipeline.lookup_snapshot_store import (
    build_stored_lookup_snapshot,
    clear_lookup_snapshot_store,
    evidence_records_to_dicts,
    save_lookup_snapshot,
    trace_record_to_dict,
)


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


def _snapshot_report() -> ZoningReport:
    return ZoningReport(
        address="7940 Plantation Blvd, Miramar, FL 33023",
        formatted_address="7940 Plantation Blvd, Miramar, FL 33023",
        municipality="Miramar",
        county="Broward",
        zoning_district="RS-4",
        max_height="35 ft",
        property_record=PropertyRecord(
            folio="504210230010",
            address="7940 PLANTATION BLVD",
            municipality="Miramar",
            county="Broward",
            zoning_code="RS-4",
            lot_size_sqft=8000.0,
        ),
        source_refs=[
            SourceRef(
                section="Sec. 500",
                section_title="Dimensional Standards",
                chunk_text_preview="RS-4 height and parking standards.",
                score=0.91,
            )
        ],
        confidence="medium",
    )


def _case_json() -> dict[str, object]:
    return {
        "case_id": "miramar-rs4-lookup",
        "jurisdiction": "Miramar, Broward County, FL",
        "expected_fields": [
            {
                "key": "parcel.apn",
                "value": "504210230010",
                "display_state": "verified",
            },
            {
                "key": "zoning.district",
                "value": "RS-4",
                "display_state": "verified",
            },
        ],
    }


def _persisted_record() -> PersistedLookupSnapshotRecord:
    snapshot = build_lookup_snapshot(_snapshot_report())
    stored = build_stored_lookup_snapshot(snapshot)
    return PersistedLookupSnapshotRecord(
        snapshot_json=lookup_snapshot_to_dict(snapshot),
        evidence_records=tuple(evidence_records_to_dicts(stored.evidence_records)),
        trace_record=trace_record_to_dict(stored.trace_record),
    )


@pytest.mark.asyncio
async def test_lookup_snapshot_eval_endpoint_scores_memory_snapshot(
    transport: ASGITransport,
) -> None:
    # Given: a memory-backed lookup snapshot and a lookup-correctness golden case.
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(_snapshot_report())
    save_lookup_snapshot(snapshot)

    # When: the snapshot is evaluated through the public lookup snapshot API.
    with (
        patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock),
        patch(
            "plotlot.api.lookup_snapshots._persist_lookup_snapshot_eval",
            new_callable=AsyncMock,
        ) as persist_eval,
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/lookup-snapshots/{snapshot.lookup_snapshot_id}/evals",
                json=_case_json(),
            )

    # Then: the API returns deterministic metrics and persists the eval result.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["metrics"]["citation_coverage"] == 1.0
    assert body["diffs"]["field_diffs"] == []
    persist_eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_lookup_snapshot_eval_endpoint_scores_persisted_snapshot(
    transport: ASGITransport,
) -> None:
    # Given: memory is empty and a durable lookup snapshot payload can be loaded.
    clear_lookup_snapshot_store()
    persisted = _persisted_record()
    snapshot_id = str(persisted.snapshot_json["lookup_snapshot_id"])

    # When: the eval endpoint scores the snapshot from durable JSON.
    with (
        patch(
            "plotlot.api.main.rate_limiter.check",
            new_callable=AsyncMock,
        ),
        patch(
            "plotlot.api.lookup_snapshots._get_persisted_lookup_snapshot",
            new_callable=AsyncMock,
            return_value=persisted,
        ),
        patch(
            "plotlot.api.lookup_snapshots._persist_lookup_snapshot_eval",
            new_callable=AsyncMock,
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/lookup-snapshots/{snapshot_id}/evals",
                json=_case_json(),
            )

    # Then: persisted snapshots can be regression-scored after process restart.
    assert response.status_code == 200
    body = response.json()
    assert body["lookup_snapshot_id"] == snapshot_id
    assert body["status"] == "passed"


@pytest.mark.asyncio
async def test_lookup_snapshot_eval_endpoint_fails_when_eval_persistence_fails(
    transport: ASGITransport,
) -> None:
    # Given: scoring succeeds but the eval result cannot be durably recorded.
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(_snapshot_report())
    save_lookup_snapshot(snapshot)

    # When: eval persistence raises a database error.
    with (
        patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock),
        patch(
            "plotlot.api.lookup_snapshots._persist_lookup_snapshot_eval",
            new_callable=AsyncMock,
            side_effect=SQLAlchemyError("db unavailable"),
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/lookup-snapshots/{snapshot.lookup_snapshot_id}/evals",
                json=_case_json(),
            )

    # Then: the API refuses to report an unrecorded eval as successful.
    assert response.status_code == 503
    assert response.json()["detail"] == "Lookup snapshot eval persistence failed"
