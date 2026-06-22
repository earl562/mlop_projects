from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.core.types import PropertyRecord, SourceRef, ZoningReport
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_eval_batch import LookupSnapshotEvalBatchMetrics
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot


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


def _case_json(case_id: str, zoning_value: str = "RS-4") -> dict[str, object]:
    return {
        "case_id": case_id,
        "jurisdiction": "Miramar, Broward County, FL",
        "expected_fields": [
            {
                "key": "parcel.apn",
                "value": "504210230010",
                "display_state": "verified",
            },
            {
                "key": "zoning.district",
                "value": zoning_value,
                "display_state": "verified",
            },
        ],
    }


def _baseline_metrics() -> LookupSnapshotEvalBatchMetrics:
    return LookupSnapshotEvalBatchMetrics(
        pass_rate=0.25,
        case_count=4,
        passed_count=1,
        failed_count=3,
        field_value_accuracy=0.5,
        display_state_accuracy=1.0,
        citation_coverage=1.0,
        warning_coverage=1.0,
        deterministic_calculation_reproducibility=1.0,
        unsupported_claim_rate=0.0,
    )


@pytest.mark.asyncio
async def test_lookup_snapshot_batch_eval_endpoint_scores_with_baseline_delta(
    transport: ASGITransport,
) -> None:
    # Given: one lookup snapshot and two golden cases, one passing and one failing.
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(_snapshot_report())
    save_lookup_snapshot(snapshot)
    request_json = {
        "suite": "lookup_correctness",
        "cases": [
            {"snapshot_id": str(snapshot.lookup_snapshot_id), "case": _case_json("passing-case")},
            {
                "snapshot_id": str(snapshot.lookup_snapshot_id),
                "case": _case_json("failing-case", "RM-10"),
            },
        ],
    }

    # When: the batch eval endpoint scores and records the batch.
    with (
        patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock),
        patch(
            "plotlot.api.lookup_snapshots._load_lookup_snapshot_eval_batch_baseline",
            new_callable=AsyncMock,
            return_value=_baseline_metrics(),
        ) as load_baseline,
        patch(
            "plotlot.api.lookup_snapshots._persist_lookup_snapshot_eval_batch",
            new_callable=AsyncMock,
        ) as persist_batch,
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/lookup-snapshots/evals/batch",
                json=request_json,
            )

    # Then: aggregate metrics, case diffs, and baseline deltas are returned.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["metrics"]["pass_rate"] == 0.5
    assert body["metric_deltas"]["pass_rate"] == 0.25
    pass_rate_log = next(
        entry for entry in body["improvement_log"] if entry["metric"] == "pass_rate"
    )
    assert pass_rate_log["direction"] == "improved"
    assert pass_rate_log["changed_rule"] == "eval_metric:pass_rate"
    assert pass_rate_log["affected_golden_cases"] == ["passing-case", "failing-case"]
    assert body["case_results"][0]["status"] == "passed"
    assert body["case_results"][1]["diffs"]["field_diffs"][0]["reason"] == "value_mismatch"
    load_baseline.assert_awaited_once_with("lookup_correctness")
    persist_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_lookup_snapshot_batch_eval_endpoint_returns_404_for_missing_snapshot(
    transport: ASGITransport,
) -> None:
    # Given: a batch references a lookup snapshot that does not exist.
    clear_lookup_snapshot_store()

    # When: the batch eval endpoint tries to load the snapshot.
    with patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/lookup-snapshots/evals/batch",
                json={
                    "suite": "lookup_correctness",
                    "cases": [{"snapshot_id": "ls_missing", "case": _case_json("missing")}],
                },
            )

    # Then: missing lookup evidence blocks scoring.
    assert response.status_code == 404
    assert response.json()["detail"] == "Lookup snapshot not found: ls_missing"
