from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.pipeline.lookup_snapshot_eval import (
    LOOKUP_CORRECTNESS_SUITE,
    LookupSnapshotEvalResult,
)
from plotlot.pipeline.lookup_snapshot_eval_json import (
    diffs_to_json,
    golden_case_to_json,
    metrics_to_json,
)
from plotlot.storage.models import EvalCaseResult, EvalRun, GoldSetCase


@dataclass(frozen=True, slots=True)
class StoredLookupSnapshotEval:
    gold_set_case_id: str
    eval_run_id: str
    eval_case_result_id: str


async def persist_lookup_snapshot_eval_result(
    session: AsyncSession,
    result: LookupSnapshotEvalResult,
) -> StoredLookupSnapshotEval:
    now = datetime.now(UTC)
    gold_case_id = _gold_case_id(result)
    eval_run_id = _eval_run_id(result)
    case_result_id = _case_result_id(eval_run_id, result)

    await _upsert_gold_case(session, gold_case_id, result, now)
    await _upsert_eval_run(session, eval_run_id, result, now)
    await _upsert_case_result(session, case_result_id, eval_run_id, gold_case_id, result)
    await session.commit()
    return StoredLookupSnapshotEval(
        gold_set_case_id=gold_case_id,
        eval_run_id=eval_run_id,
        eval_case_result_id=case_result_id,
    )


async def _upsert_gold_case(
    session: AsyncSession,
    gold_case_id: str,
    result: LookupSnapshotEvalResult,
    now: datetime,
) -> None:
    row = await session.get(GoldSetCase, gold_case_id)
    expected_json = golden_case_to_json(result.case)
    if row is None:
        session.add(
            GoldSetCase(
                id=gold_case_id,
                suite=LOOKUP_CORRECTNESS_SUITE,
                case_id=result.case.case_id,
                jurisdiction=result.case.jurisdiction,
                address=None,
                expected_json=expected_json,
                source_urls=list(result.case.source_urls),
                tags=list(result.case.tags),
                created_at=now,
                updated_at=now,
            )
        )
    else:
        setattr(row, "jurisdiction", result.case.jurisdiction)
        setattr(row, "expected_json", expected_json)
        setattr(row, "source_urls", list(result.case.source_urls))
        setattr(row, "tags", list(result.case.tags))
        setattr(row, "updated_at", now)
    await session.flush()


async def _upsert_eval_run(
    session: AsyncSession,
    eval_run_id: str,
    result: LookupSnapshotEvalResult,
    now: datetime,
) -> None:
    metrics_json = metrics_to_json(result.metrics)
    row = await session.get(EvalRun, eval_run_id)
    if row is None:
        session.add(
            EvalRun(
                id=eval_run_id,
                suite=LOOKUP_CORRECTNESS_SUITE,
                git_sha=None,
                model_profile="deterministic_lookup_snapshot_eval",
                status=result.status,
                metrics_json=metrics_json,
                created_at=now,
                completed_at=now,
            )
        )
    else:
        setattr(row, "status", result.status)
        setattr(row, "metrics_json", metrics_json)
        setattr(row, "completed_at", now)
    await session.flush()


async def _upsert_case_result(
    session: AsyncSession,
    case_result_id: str,
    eval_run_id: str,
    gold_case_id: str,
    result: LookupSnapshotEvalResult,
) -> None:
    diffs_json = diffs_to_json(result)
    evidence_metrics_json = {
        "citation_coverage": result.metrics.citation_coverage,
        "unsupported_claim_rate": result.metrics.unsupported_claim_rate,
        "warning_coverage": result.metrics.warning_coverage,
        "ingestion_quality_flag_coverage": result.metrics.ingestion_quality_flag_coverage,
    }
    trajectory_metrics_json = {
        "deterministic_calculation_reproducibility": (
            result.metrics.deterministic_calculation_reproducibility
        ),
        "missing_calculation_count": len(result.missing_calculations),
    }
    row = await session.get(EvalCaseResult, case_result_id)
    if row is None:
        session.add(
            EvalCaseResult(
                id=case_result_id,
                eval_run_id=eval_run_id,
                gold_set_case_id=gold_case_id,
                status=result.status,
                diffs_json=diffs_json,
                evidence_metrics_json=evidence_metrics_json,
                trajectory_metrics_json=trajectory_metrics_json,
            )
        )
    else:
        setattr(row, "status", result.status)
        setattr(row, "diffs_json", diffs_json)
        setattr(row, "evidence_metrics_json", evidence_metrics_json)
        setattr(row, "trajectory_metrics_json", trajectory_metrics_json)
    await session.flush()


def _gold_case_id(result: LookupSnapshotEvalResult) -> str:
    return str(
        uuid5(NAMESPACE_URL, f"plotlot:{LOOKUP_CORRECTNESS_SUITE}:case:{result.case.case_id}")
    )


def _eval_run_id(result: LookupSnapshotEvalResult) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"plotlot:{LOOKUP_CORRECTNESS_SUITE}:run:{result.lookup_snapshot_id}",
        )
    )


def _case_result_id(eval_run_id: str, result: LookupSnapshotEvalResult) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"plotlot:{LOOKUP_CORRECTNESS_SUITE}:result:{eval_run_id}:{result.case.case_id}",
        )
    )
