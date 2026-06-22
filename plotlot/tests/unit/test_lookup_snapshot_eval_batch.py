from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol, TypeVar, cast

import pytest

from plotlot.core.lookup_snapshot import DisplayState
from plotlot.core.types import PropertyRecord, SourceRef, ZoningReport
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_eval import ExpectedLookupField, LookupSnapshotGoldenCase
from plotlot.pipeline.lookup_snapshot_eval_batch import (
    LookupSnapshotEvalBatch,
    LookupSnapshotEvalBatchCase,
    LookupSnapshotEvalBatchMetrics,
    run_lookup_snapshot_eval_batch,
)
from plotlot.pipeline.lookup_snapshot_eval_batch_repository import (
    load_latest_lookup_snapshot_eval_batch_baseline,
    persist_lookup_snapshot_eval_batch,
)
from plotlot.storage.models import EvalCaseResult, EvalRun, GoldSetCase

T = TypeVar("T")


class IdentifiedRow(Protocol):
    id: str


class FakeEvalBatchSession:
    def __init__(self) -> None:
        self.rows: dict[tuple[type[object], str], object] = {}
        self.execute_rows: tuple[EvalRun, ...] = ()
        self.added: list[object] = []
        self.flushed = 0
        self.committed = 0

    async def get(self, model: type[T], key: str) -> T | None:
        row = self.rows.get((cast(type[object], model), key))
        if isinstance(row, model):
            return row
        return None

    def add(self, row: IdentifiedRow) -> None:
        self.added.append(row)
        self.rows[(type(row), row.id)] = row

    async def execute(self, statement: object) -> FakeExecuteResult:
        return FakeExecuteResult(self.execute_rows)

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.committed += 1


class FakeExecuteResult:
    def __init__(self, rows: tuple[EvalRun, ...]) -> None:
        self._rows = rows

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._rows)


class FakeScalarResult:
    def __init__(self, rows: tuple[EvalRun, ...]) -> None:
        self._rows = rows

    def all(self) -> tuple[EvalRun, ...]:
        return self._rows


def _report(*, with_ordinance: bool = True) -> ZoningReport:
    source_refs = (
        [
            SourceRef(
                section="Sec. 500",
                section_title="Dimensional Standards",
                chunk_text_preview="RS-4 height and parking standards.",
                score=0.91,
            )
        ]
        if with_ordinance
        else []
    )
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
        source_refs=source_refs,
        confidence="medium",
    )


def _golden_case(case_id: str) -> LookupSnapshotGoldenCase:
    return LookupSnapshotGoldenCase(
        case_id=case_id,
        jurisdiction="Miramar, Broward County, FL",
        expected_fields=(
            ExpectedLookupField(
                key="parcel.apn",
                value="504210230010",
                display_state=DisplayState.VERIFIED,
            ),
            ExpectedLookupField(
                key="zoning.district",
                value="RS-4",
                display_state=DisplayState.VERIFIED,
            ),
        ),
    )


def _baseline_metrics() -> LookupSnapshotEvalBatchMetrics:
    return LookupSnapshotEvalBatchMetrics(
        pass_rate=0.25,
        case_count=4,
        passed_count=1,
        failed_count=3,
        field_value_accuracy=0.5,
        display_state_accuracy=0.5,
        citation_coverage=0.5,
        warning_coverage=1.0,
        deterministic_calculation_reproducibility=1.0,
        unsupported_claim_rate=0.2,
    )


def _stronger_baseline_metrics() -> LookupSnapshotEvalBatchMetrics:
    return LookupSnapshotEvalBatchMetrics(
        pass_rate=1.0,
        case_count=2,
        passed_count=2,
        failed_count=0,
        field_value_accuracy=1.0,
        display_state_accuracy=1.0,
        citation_coverage=1.0,
        warning_coverage=1.0,
        deterministic_calculation_reproducibility=1.0,
        unsupported_claim_rate=0.0,
    )


def _batch() -> LookupSnapshotEvalBatch:
    return LookupSnapshotEvalBatch(
        suite="lookup_correctness",
        cases=(
            LookupSnapshotEvalBatchCase(
                snapshot=build_lookup_snapshot(_report()),
                case=_golden_case("miramar-rs4-pass"),
            ),
            LookupSnapshotEvalBatchCase(
                snapshot=build_lookup_snapshot(_report(with_ordinance=False)),
                case=_golden_case("miramar-rs4-missing-ordinance"),
            ),
        ),
        baseline=_baseline_metrics(),
    )


def test_run_lookup_snapshot_eval_batch_aggregates_cases_and_baseline_delta() -> None:
    # Given: a batch with one passing lookup and one missing required ordinance evidence.
    batch = _batch()

    # When: the lookup-correctness batch is scored.
    result = run_lookup_snapshot_eval_batch(batch)

    # Then: aggregate metrics and improvement deltas reflect every golden case.
    assert result.status == "failed"
    assert result.metrics.pass_rate == 0.5
    assert result.metrics.case_count == 2
    assert result.metrics.passed_count == 1
    assert result.metrics.failed_count == 1
    assert result.metrics.citation_coverage == 0.75
    assert result.metric_deltas is not None
    assert result.metric_deltas.pass_rate == 0.25
    assert result.metric_deltas.citation_coverage == 0.25
    assert result.metric_deltas.unsupported_claim_rate == -0.2
    assert result.gate_failures == ()
    assert result.case_results[1].diffs[0].reason == "missing_required_evidence"


def test_run_lookup_snapshot_eval_batch_records_regression_gate_failures() -> None:
    # Given: a batch that regresses against a stronger previous baseline.
    batch = LookupSnapshotEvalBatch(
        suite="lookup_correctness",
        cases=_batch().cases,
        baseline=_stronger_baseline_metrics(),
    )

    # When: the lookup-correctness batch is scored.
    result = run_lookup_snapshot_eval_batch(batch)

    # Then: release-blocking regression gates name the weaker metrics.
    assert result.status == "failed"
    assert {failure.metric for failure in result.gate_failures} == {
        "pass_rate",
        "display_state_accuracy",
        "citation_coverage",
    }
    assert result.gate_failures[0].current == 0.5
    assert result.gate_failures[0].baseline == 1.0


@pytest.mark.asyncio
async def test_persist_lookup_snapshot_eval_batch_writes_one_run_for_all_cases() -> None:
    # Given: a scored batch and an empty eval storage session.
    session = FakeEvalBatchSession()
    result = run_lookup_snapshot_eval_batch(_batch())

    # When: the batch result is persisted.
    stored = await persist_lookup_snapshot_eval_batch(session, result)

    # Then: one aggregate run owns every per-case result.
    assert session.committed == 1
    assert len(stored.gold_set_case_ids) == 2
    assert len(stored.eval_case_result_ids) == 2

    eval_run = await session.get(EvalRun, stored.eval_run_id)
    assert eval_run is not None
    assert eval_run.status == "failed"
    assert eval_run.metrics_json["pass_rate"] == 0.5
    assert eval_run.metrics_json["metric_deltas"]["pass_rate"] == 0.25
    assert eval_run.metrics_json["gate_failures"] == []

    case_results = [row for row in session.added if isinstance(row, EvalCaseResult)]
    assert len(case_results) == 2
    assert {case_result.eval_run_id for case_result in case_results} == {stored.eval_run_id}

    gold_cases = [row for row in session.added if isinstance(row, GoldSetCase)]
    assert [gold_case.case_id for gold_case in gold_cases] == [
        "miramar-rs4-pass",
        "miramar-rs4-missing-ordinance",
    ]


@pytest.mark.asyncio
async def test_load_latest_lookup_snapshot_eval_batch_baseline_skips_malformed_runs() -> None:
    # Given: the newest eval row is incomplete and the next row has complete metrics.
    session = FakeEvalBatchSession()
    now = datetime.now(UTC)
    session.execute_rows = (
        EvalRun(
            id="malformed-run",
            suite="lookup_correctness",
            model_profile="deterministic_lookup_snapshot_batch_eval",
            status="passed",
            metrics_json={"pass_rate": 1.0},
            created_at=now,
            completed_at=now,
        ),
        EvalRun(
            id="parseable-run",
            suite="lookup_correctness",
            model_profile="deterministic_lookup_snapshot_batch_eval",
            status="failed",
            metrics_json=asdict(_baseline_metrics()),
            created_at=now,
            completed_at=now,
        ),
    )

    # When: the latest usable baseline is loaded for the suite.
    baseline = await load_latest_lookup_snapshot_eval_batch_baseline(
        session,
        "lookup_correctness",
    )

    # Then: malformed metrics are not trusted as a baseline.
    assert baseline == _baseline_metrics()
