from __future__ import annotations

from typing import TypeVar

import pytest

from plotlot.core.lookup_snapshot import DisplayState
from plotlot.core.types import PropertyRecord, SourceRef, ZoningReport
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_eval import (
    ExpectedLookupField,
    LookupSnapshotGoldenCase,
    score_lookup_snapshot,
)
from plotlot.pipeline.lookup_snapshot_eval_repository import persist_lookup_snapshot_eval_result
from plotlot.storage.models import EvalCaseResult, EvalRun, GoldSetCase

T = TypeVar("T")


class FakeEvalSession:
    def __init__(self) -> None:
        self.rows: dict[tuple[type, str], T] = {}
        self.added: list[T] = []
        self.flushed = 0
        self.committed = 0

    async def get(self, model: type[T], key: str) -> T | None:
        row = self.rows.get((model, key))
        if isinstance(row, model):
            return row
        return None

    def add(self, row: T) -> None:
        self.added.append(row)
        self.rows[(type(row), row.id)] = row

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.committed += 1


def _report(*, with_ordinance: bool = True, parcel_zoning_code: str = "RS-4") -> ZoningReport:
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
            zoning_code=parcel_zoning_code,
            lot_size_sqft=8000.0,
        ),
        source_refs=source_refs,
        confidence="medium",
    )


def _golden_case() -> LookupSnapshotGoldenCase:
    return LookupSnapshotGoldenCase(
        case_id="miramar-rs4-lookup",
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


def test_score_lookup_snapshot_passes_when_expected_fields_have_evidence() -> None:
    # Given: a lookup snapshot with parcel and ordinance evidence.
    snapshot = build_lookup_snapshot(_report())
    case = _golden_case()

    # When: the snapshot is scored against a lookup-correctness golden case.
    result = score_lookup_snapshot(snapshot, case)

    # Then: field values, display state, and citation coverage all pass.
    assert result.status == "passed"
    assert result.metrics.field_value_accuracy == 1.0
    assert result.metrics.display_state_accuracy == 1.0
    assert result.metrics.citation_coverage == 1.0
    assert result.diffs == ()


def test_score_lookup_snapshot_fails_when_expected_zoning_evidence_is_missing() -> None:
    # Given: a lookup snapshot that names a zoning district without ordinance evidence.
    snapshot = build_lookup_snapshot(_report(with_ordinance=False))
    case = _golden_case()

    # When: the snapshot is scored against a case that requires cited zoning.
    result = score_lookup_snapshot(snapshot, case)

    # Then: the missing evidence is a lookup-correctness failure, not a pass.
    assert result.status == "failed"
    assert result.metrics.citation_coverage == 0.5
    assert result.diffs[0].field_key == "zoning.district"
    assert result.diffs[0].reason == "missing_required_evidence"


def test_score_lookup_snapshot_scores_expected_ingestion_quality_flags() -> None:
    # Given: a lookup snapshot whose zoning fields are unknown because ordinance evidence is missing.
    snapshot = build_lookup_snapshot(_report(with_ordinance=False))
    case = LookupSnapshotGoldenCase(
        case_id="miramar-rs4-quality-flags",
        jurisdiction="Miramar, Broward County, FL",
        expected_fields=(
            ExpectedLookupField(
                key="zoning.district",
                value="RS-4",
                display_state=DisplayState.UNKNOWN,
                requires_evidence=False,
            ),
        ),
        expected_quality_flags=("missing_evidence",),
    )

    # When: the snapshot is scored against expected ingestion quality flags.
    result = score_lookup_snapshot(snapshot, case)

    # Then: quality-flag coverage is measured separately from warning coverage.
    assert result.status == "passed"
    assert result.metrics.ingestion_quality_flag_coverage == 1.0
    assert result.missing_quality_flags == ()


def test_score_lookup_snapshot_scores_contradictory_zoning_quality_flag() -> None:
    # Given: parcel zoning conflicts with official zoning evidence.
    snapshot = build_lookup_snapshot(_report(parcel_zoning_code="RM-2"))
    case = LookupSnapshotGoldenCase(
        case_id="miramar-rs4-contradictory-zoning",
        jurisdiction="Miramar, Broward County, FL",
        expected_fields=(
            ExpectedLookupField(
                key="zoning.district",
                value="RS-4",
                display_state=DisplayState.CONTRADICTED,
            ),
        ),
        expected_quality_flags=("contradictory_sources",),
    )

    # When: the contradicted lookup snapshot is scored.
    result = score_lookup_snapshot(snapshot, case)

    # Then: contradiction detection is visible to release-gate quality scoring.
    assert result.status == "passed"
    assert result.metrics.ingestion_quality_flag_coverage == 1.0
    assert result.missing_quality_flags == ()


def test_score_lookup_snapshot_fails_when_expected_quality_flag_is_missing() -> None:
    # Given: a golden case expects a schema-drift flag the lookup did not surface.
    snapshot = build_lookup_snapshot(_report())
    case = LookupSnapshotGoldenCase(
        case_id="miramar-rs4-missing-quality-flag",
        jurisdiction="Miramar, Broward County, FL",
        expected_fields=(
            ExpectedLookupField(
                key="parcel.apn",
                value="504210230010",
                display_state=DisplayState.VERIFIED,
            ),
        ),
        expected_quality_flags=("schema_drift",),
    )

    # When: the snapshot is scored.
    result = score_lookup_snapshot(snapshot, case)

    # Then: missing quality flags fail the golden case before release.
    assert result.status == "failed"
    assert result.metrics.ingestion_quality_flag_coverage == 0.0
    assert result.missing_quality_flags == ("schema_drift",)


@pytest.mark.asyncio
async def test_persist_lookup_snapshot_eval_result_writes_eval_spine_rows() -> None:
    # Given: a scored lookup snapshot eval result and an empty harness eval session.
    session = FakeEvalSession()
    snapshot = build_lookup_snapshot(_report())
    result = score_lookup_snapshot(snapshot, _golden_case())

    # When: the result is persisted.
    stored = await persist_lookup_snapshot_eval_result(session, result)

    # Then: the durable gold case, eval run, and case result rows are written.
    assert session.committed == 1
    gold_case = await session.get(GoldSetCase, stored.gold_set_case_id)
    eval_run = await session.get(EvalRun, stored.eval_run_id)
    case_result = await session.get(EvalCaseResult, stored.eval_case_result_id)

    assert gold_case is not None
    assert gold_case.case_id == "miramar-rs4-lookup"
    assert gold_case.expected_json["expected_fields"][0]["key"] == "parcel.apn"

    assert eval_run is not None
    assert eval_run.suite == "lookup_correctness"
    assert eval_run.status == "passed"
    assert eval_run.metrics_json["citation_coverage"] == 1.0

    assert case_result is not None
    assert case_result.status == "passed"
    assert case_result.diffs_json["lookup_snapshot_id"] == str(snapshot.lookup_snapshot_id)
    assert case_result.evidence_metrics_json["citation_coverage"] == 1.0
    assert case_result.trajectory_metrics_json["deterministic_calculation_reproducibility"] == 1.0
