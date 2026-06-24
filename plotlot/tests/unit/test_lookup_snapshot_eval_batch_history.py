from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, TypeVar

import pytest
from sqlalchemy.sql import Select

from plotlot.pipeline.lookup_snapshot_eval_batch_history import (
    load_lookup_snapshot_eval_batch_history,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.models import EvalRun

T = TypeVar("T")


class ScalarResult(Protocol[T]):
    def all(self) -> tuple[T, ...]: ...


class ExecuteResult(Protocol[T]):
    def scalars(self) -> ScalarResult[T]: ...


class FakeEvalHistorySession:
    def __init__(self, rows: tuple[EvalRun, ...]) -> None:
        self.rows = rows
        self.executed = 0

    async def execute(self, _statement: Select[tuple[EvalRun]]) -> ExecuteResult[EvalRun]:
        self.executed += 1
        return FakeExecuteResult(self.rows)


class FakeExecuteResult:
    def __init__(self, rows: tuple[EvalRun, ...]) -> None:
        self._rows = rows

    def scalars(self) -> ScalarResult[EvalRun]:
        return FakeScalarResult(self._rows)


class FakeScalarResult:
    def __init__(self, rows: tuple[EvalRun, ...]) -> None:
        self._rows = rows

    def all(self) -> tuple[EvalRun, ...]:
        return self._rows


@pytest.mark.asyncio
async def test_load_lookup_snapshot_eval_batch_history_skips_malformed_rows() -> None:
    now = datetime.now(UTC)
    session = FakeEvalHistorySession(
        rows=(
            EvalRun(
                id="malformed",
                suite="lookup_correctness",
                model_profile="deterministic_lookup_snapshot_batch_eval",
                status="failed",
                metrics_json={"pass_rate": "bad"},
                created_at=now,
                completed_at=now,
            ),
            EvalRun(
                id="run-1",
                suite="lookup_correctness",
                model_profile="deterministic_lookup_snapshot_batch_eval",
                status="failed",
                metrics_json=_history_payload(),
                created_at=now,
                completed_at=now,
            ),
        )
    )

    records = await load_lookup_snapshot_eval_batch_history(
        session,
        suite="lookup_correctness",
        limit=10,
    )

    assert session.executed == 1
    assert len(records) == 1
    assert records[0].eval_run_id == "run-1"
    assert records[0].payload["improvement_log"][0]["changed_rule"] == ("eval_metric:pass_rate")


def _history_payload() -> dict[str, JsonValue]:
    return {
        "suite": "lookup_correctness",
        "status": "failed",
        "case_ids": ["case-a"],
        "lookup_snapshot_ids": ["ls_case-a"],
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
        "baseline": {"pass_rate": 1.0},
        "metric_deltas": {"pass_rate": -0.5},
        "gate_failures": [
            {
                "metric": "pass_rate",
                "reason": "regressed",
                "current": 0.5,
                "baseline": 1.0,
            }
        ],
        "improvement_log": [
            {
                "source": "lookup_snapshot_eval_batch",
                "researched_input": "lookup_correctness",
                "changed_rule": "eval_metric:pass_rate",
                "metric": "pass_rate",
                "direction": "regressed",
                "reason": "baseline_delta",
                "affected_golden_cases": ["case-a"],
                "before_score": 1.0,
                "after_score": 0.5,
                "delta": -0.5,
                "gate_blocking": True,
                "unresolved_risk": "baseline_regression_requires_review",
            }
        ],
    }
