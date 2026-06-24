from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.core.types import PropertyRecord, ZoningReport
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot


def _missing_ordinance_report() -> ZoningReport:
    return ZoningReport(
        address="7940 Plantation Blvd, Miramar, FL 33023",
        formatted_address="7940 Plantation Blvd, Miramar, FL 33023",
        municipality="Miramar",
        county="Broward",
        zoning_district="RS-4",
        property_record=PropertyRecord(
            folio="504210230010",
            address="7940 PLANTATION BLVD",
            municipality="Miramar",
            county="Broward",
            zoning_code="RS-4",
            lot_size_sqft=8000.0,
        ),
        source_refs=[],
        confidence="medium",
    )


@pytest.mark.asyncio
async def test_batch_eval_endpoint_returns_ingestion_quality_flag_metric() -> None:
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(_missing_ordinance_report())
    save_lookup_snapshot(snapshot)

    with (
        patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock),
        patch(
            "plotlot.api.lookup_snapshots._persist_lookup_snapshot_eval_batch",
            new_callable=AsyncMock,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/lookup-snapshots/evals/batch",
                json={
                    "suite": "lookup_correctness",
                    "use_latest_baseline": False,
                    "cases": [
                        {
                            "snapshot_id": str(snapshot.lookup_snapshot_id),
                            "case": {
                                "case_id": "quality-flag-case",
                                "jurisdiction": "Miramar, Broward County, FL",
                                "expected_fields": [
                                    {
                                        "key": "zoning.district",
                                        "value": "RS-4",
                                        "display_state": "unknown",
                                        "requires_evidence": False,
                                    }
                                ],
                                "expected_quality_flags": ["missing_evidence"],
                            },
                        }
                    ],
                },
            )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "passed"
    assert body["metrics"]["ingestion_quality_flag_coverage"] == 1.0
    assert body["case_results"][0]["metrics"]["ingestion_quality_flag_coverage"] == 1.0
    assert body["case_results"][0]["diffs"]["missing_quality_flags"] == []
