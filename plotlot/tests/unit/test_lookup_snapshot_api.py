from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from plotlot.api.main import app
from plotlot.core.types import PropertyRecord, ZoningReport
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_repository import PersistedLookupSnapshotRecord
from plotlot.pipeline.lookup_snapshot_serialization import lookup_snapshot_to_dict
from plotlot.pipeline.lookup_snapshot_store import (
    build_stored_lookup_snapshot,
    evidence_records_to_dicts,
    trace_record_to_dict,
)


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
        sources=["Sec. 500 — Dimensional Standards"],
        confidence="medium",
    )


def _persisted_record() -> PersistedLookupSnapshotRecord:
    snapshot = build_lookup_snapshot(_snapshot_report())
    stored = build_stored_lookup_snapshot(snapshot)
    return PersistedLookupSnapshotRecord(
        snapshot_json=lookup_snapshot_to_dict(snapshot),
        evidence_records=tuple(evidence_records_to_dicts(stored.evidence_records)),
        trace_record=trace_record_to_dict(stored.trace_record),
    )


def test_lookup_snapshot_routes_advertise_source_metadata_contract() -> None:
    # Given: API clients depend on lookup snapshot source lineage for display correctness.
    schema = app.openapi()

    # When: the create/read route response schema is inspected.
    create_response = schema["paths"]["/api/v1/lookup-snapshots"]["post"]["responses"]["200"]
    read_response = schema["paths"]["/api/v1/lookup-snapshots/{snapshot_id}"]["get"]["responses"][
        "200"
    ]
    response_ref = create_response["content"]["application/json"]["schema"]["$ref"]
    read_response_ref = read_response["content"]["application/json"]["schema"]["$ref"]
    snapshot_schema_name = response_ref.rsplit("/", maxsplit=1)[-1]
    source_schema_ref = schema["components"]["schemas"][snapshot_schema_name]["properties"][
        "source_metadata"
    ]["items"]["$ref"]
    source_schema_name = source_schema_ref.rsplit("/", maxsplit=1)[-1]
    source_properties = schema["components"]["schemas"][source_schema_name]["properties"]

    # Then: both routes use the same explicit lookup snapshot contract with source lineage.
    assert read_response_ref == response_ref
    assert {
        "evidence_id",
        "source_url",
        "source_title",
        "source_type",
        "source_authority",
        "publisher",
        "retrieved_at",
        "effective_date",
        "parser_version",
        "schema_version",
        "raw_artifact_ref",
        "query_parameters",
    }.issubset(source_properties)


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_lookup_snapshot_endpoints_create_and_read_traceable_snapshot(
    transport: ASGITransport,
) -> None:
    from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store

    clear_lookup_snapshot_store()
    with (
        patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock),
        patch(
            "plotlot.api.lookup_snapshot_creation.lookup_address",
            new_callable=AsyncMock,
            return_value=_snapshot_report(),
        ),
        patch(
            "plotlot.api.lookup_snapshot_creation.persist_created_lookup_snapshot",
            new_callable=AsyncMock,
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/lookup-snapshots",
                json={"address": "7940 Plantation Blvd, Miramar, FL 33023"},
            )

            assert created.status_code == 200
            snapshot = created.json()
            snapshot_id = snapshot["lookup_snapshot_id"]
            assert snapshot["fields"]

            fetched = await client.get(f"/api/v1/lookup-snapshots/{snapshot_id}")
            evidence = await client.get(f"/api/v1/lookup-snapshots/{snapshot_id}/evidence")
            trace = await client.get(f"/api/v1/lookup-snapshots/{snapshot_id}/trace")

    assert fetched.status_code == 200
    assert fetched.json()["lookup_snapshot_id"] == snapshot_id
    assert evidence.status_code == 200
    evidence_records = evidence.json()
    assert evidence_records
    assert evidence_records[0]["evidence_id"].startswith("ev_")
    assert evidence_records[0]["retrieved_at"]
    assert evidence_records[0]["parser_version"]
    assert evidence_records[0]["schema_version"]
    assert evidence_records[0]["normalized_fields"]
    assert trace.status_code == 200
    trace_body = trace.json()
    assert trace_body["lookup_snapshot_id"] == snapshot_id
    assert trace_body["evidence_ids"]
    assert trace_body["source_retrievals"]
    source_retrieval = trace_body["source_retrievals"][0]
    assert source_retrieval["evidence_id"].startswith("ev_")
    assert "source_url" in source_retrieval
    assert source_retrieval["retrieved_at"]
    assert source_retrieval["parser_version"]
    assert source_retrieval["schema_version"]
    assert source_retrieval["raw_artifact_ref"]
    assert source_retrieval["lineage"]
    assert "missing_source_url" in source_retrieval["quality_flags"]
    assert trace_body["field_count"] == len(snapshot["fields"])


@pytest.mark.asyncio
async def test_lookup_snapshot_rate_limit_applies_only_to_creation(
    transport: ASGITransport,
) -> None:
    from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store

    clear_lookup_snapshot_store()
    rate_check = AsyncMock()
    with (
        patch("plotlot.api.main.rate_limiter.check", rate_check),
        patch(
            "plotlot.api.lookup_snapshot_creation.lookup_address",
            new_callable=AsyncMock,
            return_value=_snapshot_report(),
        ),
        patch(
            "plotlot.api.lookup_snapshot_creation.persist_created_lookup_snapshot",
            new_callable=AsyncMock,
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/lookup-snapshots",
                json={"address": "7940 Plantation Blvd, Miramar, FL 33023"},
            )
            snapshot_id = created.json()["lookup_snapshot_id"]
            fetched = await client.get(f"/api/v1/lookup-snapshots/{snapshot_id}")
            evidence = await client.get(f"/api/v1/lookup-snapshots/{snapshot_id}/evidence")
            trace = await client.get(f"/api/v1/lookup-snapshots/{snapshot_id}/trace")

    assert created.status_code == 200
    assert fetched.status_code == 200
    assert evidence.status_code == 200
    assert trace.status_code == 200
    assert rate_check.await_count == 1
    request = rate_check.await_args.args[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/lookup-snapshots"


@pytest.mark.asyncio
async def test_lookup_snapshot_creation_fails_when_durable_persistence_fails(
    transport: ASGITransport,
) -> None:
    from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store

    clear_lookup_snapshot_store()
    with (
        patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock),
        patch(
            "plotlot.api.lookup_snapshot_creation.lookup_address",
            new_callable=AsyncMock,
            return_value=_snapshot_report(),
        ),
        patch(
            "plotlot.api.lookup_snapshot_creation.persist_created_lookup_snapshot",
            new_callable=AsyncMock,
            side_effect=SQLAlchemyError("db unavailable"),
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/lookup-snapshots",
                json={"address": "7940 Plantation Blvd, Miramar, FL 33023"},
            )

    assert created.status_code == 503
    assert created.json()["detail"] == "Lookup snapshot persistence failed"


@pytest.mark.asyncio
async def test_lookup_snapshot_endpoints_read_durable_record_when_memory_is_empty(
    transport: ASGITransport,
) -> None:
    from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store

    clear_lookup_snapshot_store()
    persisted = _persisted_record()
    snapshot_id = str(persisted.snapshot_json["lookup_snapshot_id"])
    with patch(
        "plotlot.api.lookup_snapshots._get_persisted_lookup_snapshot",
        new_callable=AsyncMock,
        return_value=persisted,
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            snapshot = await client.get(f"/api/v1/lookup-snapshots/{snapshot_id}")
            evidence = await client.get(f"/api/v1/lookup-snapshots/{snapshot_id}/evidence")
            trace = await client.get(f"/api/v1/lookup-snapshots/{snapshot_id}/trace")

    assert snapshot.status_code == 200
    assert snapshot.json() == persisted.snapshot_json
    assert evidence.status_code == 200
    assert evidence.json() == list(persisted.evidence_records)
    assert trace.status_code == 200
    assert trace.json() == persisted.trace_record


@pytest.mark.asyncio
async def test_lookup_snapshot_endpoints_return_404_for_unknown_snapshot(
    transport: ASGITransport,
) -> None:
    from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store

    clear_lookup_snapshot_store()
    with patch(
        "plotlot.api.lookup_snapshots._get_persisted_lookup_snapshot",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            snapshot = await client.get("/api/v1/lookup-snapshots/ls_missing")
            evidence = await client.get("/api/v1/lookup-snapshots/ls_missing/evidence")
            trace = await client.get("/api/v1/lookup-snapshots/ls_missing/trace")

    assert snapshot.status_code == 404
    assert evidence.status_code == 404
    assert trace.status_code == 404
