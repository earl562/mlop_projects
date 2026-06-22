from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from plotlot.api.main import app
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_eval_batch_history import (
    LookupSnapshotEvalBatchHistoryRecord,
)
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot
from tests.unit.test_lookup_snapshot_eval_batch_api import _case_json, _snapshot_report


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_lookup_snapshot_batch_eval_history_endpoint_returns_recent_runs(
    transport: ASGITransport,
) -> None:
    # Given: a recorded lookup-correctness batch eval run.
    now = datetime.now(UTC)

    # When: the batch history endpoint is requested.
    with patch(
        "plotlot.api.lookup_snapshots._load_lookup_snapshot_eval_batch_history",
        new_callable=AsyncMock,
        return_value=(
            LookupSnapshotEvalBatchHistoryRecord(
                eval_run_id="run-1",
                suite="lookup_correctness",
                status="failed",
                created_at=now,
                completed_at=now,
                payload={
                    "pass_rate": 0.5,
                    "case_count": 1,
                    "passed_count": 0,
                    "failed_count": 1,
                    "field_value_accuracy": 1.0,
                    "display_state_accuracy": 1.0,
                    "citation_coverage": 0.5,
                    "warning_coverage": 1.0,
                    "deterministic_calculation_reproducibility": 1.0,
                    "unsupported_claim_rate": 0.0,
                    "improvement_log": [
                        {
                            "changed_rule": "eval_metric:pass_rate",
                            "direction": "regressed",
                        }
                    ],
                },
            ),
        ),
    ) as load_history:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/lookup-snapshots/evals/batch/runs",
                params={"suite": "lookup_correctness", "limit": 5},
            )

    # Then: recent run metrics and improvement logs are surfaced.
    assert response.status_code == 200
    body = response.json()
    assert body["runs"][0]["eval_run_id"] == "run-1"
    assert body["runs"][0]["metrics"]["pass_rate"] == 0.5
    assert body["runs"][0]["improvement_log"][0]["changed_rule"] == ("eval_metric:pass_rate")
    load_history.assert_awaited_once_with("lookup_correctness", 5)


@pytest.mark.asyncio
async def test_lookup_snapshot_release_gate_endpoint_blocks_on_latest_regression(
    transport: ASGITransport,
) -> None:
    # Given: the latest lookup-correctness batch eval has a regression gate failure.
    now = datetime.now(UTC)
    with patch(
        "plotlot.api.lookup_snapshots._load_lookup_snapshot_eval_batch_history",
        new_callable=AsyncMock,
        return_value=(
            LookupSnapshotEvalBatchHistoryRecord(
                eval_run_id="run-1",
                suite="lookup_correctness",
                status="failed",
                created_at=now,
                completed_at=now,
                payload={
                    "pass_rate": 0.5,
                    "case_count": 1,
                    "passed_count": 0,
                    "failed_count": 1,
                    "field_value_accuracy": 1.0,
                    "display_state_accuracy": 1.0,
                    "citation_coverage": 0.5,
                    "warning_coverage": 1.0,
                    "deterministic_calculation_reproducibility": 1.0,
                    "unsupported_claim_rate": 0.0,
                    "gate_failures": [
                        {
                            "metric": "pass_rate",
                            "reason": "regressed",
                            "current": 0.5,
                            "baseline": 1.0,
                        }
                    ],
                },
            ),
        ),
    ) as load_history:
        # When: the API release gate is checked directly.
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/lookup-snapshots/evals/batch/release-gate",
                params={"suite": "lookup_correctness"},
            )

    # Then: release is blocked with the regression evidence surfaced.
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "blocked"
    assert body["release_blocked"] is True
    assert body["reason"] == "latest_eval_failed"
    assert body["latest_run"]["eval_run_id"] == "run-1"
    assert body["blockers"][0]["code"] == "regression_gate_failed"
    assert body["blockers"][0]["metric"] == "pass_rate"
    load_history.assert_awaited_once_with("lookup_correctness", 1)


@pytest.mark.asyncio
async def test_lookup_snapshot_batch_eval_endpoint_fails_when_persistence_fails(
    transport: ASGITransport,
) -> None:
    # Given: scoring succeeds but the aggregate eval cannot be persisted.
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(_snapshot_report())
    save_lookup_snapshot(snapshot)

    # When: batch eval persistence raises a database error.
    with (
        patch("plotlot.api.main.rate_limiter.check", new_callable=AsyncMock),
        patch(
            "plotlot.api.lookup_snapshots._persist_lookup_snapshot_eval_batch",
            new_callable=AsyncMock,
            side_effect=SQLAlchemyError("db unavailable"),
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/lookup-snapshots/evals/batch",
                json={
                    "suite": "lookup_correctness",
                    "use_latest_baseline": False,
                    "cases": [
                        {
                            "snapshot_id": str(snapshot.lookup_snapshot_id),
                            "case": _case_json("passing-case"),
                        }
                    ],
                },
            )

    # Then: the API refuses to report an unrecorded batch eval as successful.
    assert response.status_code == 503
    assert response.json()["detail"] == "Lookup snapshot batch eval persistence failed"
