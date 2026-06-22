from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.core.types import (
    ConstraintResult,
    DensityAnalysis,
    PropertyRecord,
    Setbacks,
    SourceRef,
    ZoningReport,
)
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


def _miami_gardens_report() -> ZoningReport:
    return ZoningReport(
        address="171 NE 209th Ter, Miami, FL 33179",
        formatted_address="171 NE 209th Ter, Miami, FL 33179",
        municipality="Miami Gardens",
        county="Miami-Dade",
        zoning_district="R-1",
        max_height="35 ft",
        setbacks=Setbacks(front="25 ft", side="7.5 ft", rear="25 ft"),
        parking_requirements="2 spaces per unit",
        property_record=PropertyRecord(
            folio="3421130010010",
            address="171 NE 209TH TER",
            municipality="Miami Gardens",
            county="Miami-Dade",
            zoning_code="R-1",
            lot_size_sqft=7500.0,
        ),
        source_refs=[
            SourceRef(
                section="Sec. 34-342",
                section_title="Single-family residential district",
                chunk_text_preview="R-1 district permits one dwelling unit with 35-foot height limits.",
                score=0.95,
            )
        ],
        density_analysis=DensityAnalysis(
            max_units=1,
            governing_constraint="density",
            constraints=[
                ConstraintResult(
                    name="density",
                    max_units=1,
                    raw_value=1.0,
                    formula="R-1 single-family district permits one unit",
                    is_governing=True,
                )
            ],
            lot_size_sqft=7500.0,
            confidence="high",
        ),
        confidence="high",
    )


@pytest.mark.asyncio
async def test_lookup_snapshot_golden_batch_endpoint_scores_matching_fixture(
    transport: ASGITransport,
) -> None:
    # Given: a recorded lookup snapshot whose address has a canonical golden fixture.
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(_miami_gardens_report())
    save_lookup_snapshot(snapshot)

    # When: the golden-batch endpoint runs the matching fixture against the snapshot.
    with (
        patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock),
        patch(
            "plotlot.pipeline.lookup_snapshot_golden_eval_runner._load_lookup_snapshot_eval_batch_baseline",
            new_callable=AsyncMock,
            return_value=None,
        ) as load_baseline,
        patch(
            "plotlot.pipeline.lookup_snapshot_golden_eval_runner._persist_lookup_snapshot_eval_batch",
            new_callable=AsyncMock,
        ) as persist_batch,
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/lookup-snapshots/evals/batch/golden",
                json={
                    "suite": "lookup_correctness",
                    "snapshots": [
                        {
                            "snapshot_id": str(snapshot.lookup_snapshot_id),
                            "address": "171 NE 209th Ter, Miami, FL 33179",
                        }
                    ],
                },
            )

    # Then: the API records a deterministic passing batch eval for release-gate history.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["metrics"]["pass_rate"] == 1.0
    assert body["case_results"][0]["status"] == "passed"
    assert body["case_results"][0]["case_id"].startswith("golden-data-171-ne-209th")
    load_baseline.assert_awaited_once_with("lookup_correctness")
    persist_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_lookup_snapshot_golden_batch_endpoint_refuses_unmatched_fixture(
    transport: ASGITransport,
) -> None:
    # Given: a recorded snapshot but no canonical golden case for the requested address.
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(_miami_gardens_report())
    save_lookup_snapshot(snapshot)

    # When: the caller asks for a golden eval with an unknown fixture address.
    with patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/lookup-snapshots/evals/batch/golden",
                json={
                    "suite": "lookup_correctness",
                    "snapshots": [
                        {
                            "snapshot_id": str(snapshot.lookup_snapshot_id),
                            "address": "1 Missing Golden Case Way, Miami, FL 33179",
                        }
                    ],
                    "use_latest_baseline": False,
                },
            )

    # Then: missing fixture evidence is explicit and no synthetic eval is produced.
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Lookup golden case not found: 1 Missing Golden Case Way, Miami, FL 33179"
    )
