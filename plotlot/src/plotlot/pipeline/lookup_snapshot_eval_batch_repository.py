from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.pipeline.lookup_snapshot_eval import LookupSnapshotEvalResult
from plotlot.pipeline.lookup_snapshot_eval_batch import (
    LookupSnapshotEvalBatchMetrics,
    LookupSnapshotEvalBatchResult,
)
from plotlot.pipeline.lookup_snapshot_eval_batch_json import (
    batch_metrics_from_json,
    batch_result_to_json,
)
from plotlot.pipeline.lookup_snapshot_eval_json import (
    diffs_to_json,
    golden_case_to_json,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.models import EvalCaseResult, EvalRun, GoldSetCase

BATCH_EVAL_MODEL_PROFILE: Final = "deterministic_lookup_snapshot_batch_eval"


@dataclass(frozen=True, slots=True)
class StoredLookupSnapshotEvalBatch:
    eval_run_id: str
    gold_set_case_ids: tuple[str, ...]
    eval_case_result_ids: tuple[str, ...]


async def persist_lookup_snapshot_eval_batch(
    session: AsyncSession,
    result: LookupSnapshotEvalBatchResult,
) -> StoredLookupSnapshotEvalBatch:
    now = datetime.now(UTC)
    eval_run_id = _eval_run_id(result)
    gold_case_ids: list[str] = []
    case_result_ids: list[str] = []

    await _upsert_eval_run(session, eval_run_id, result, now)
    for case_result in result.case_results:
        gold_case_id = _gold_case_id(result.suite, case_result)
        case_result_id = _case_result_id(result.suite, eval_run_id, case_result)
        await _upsert_gold_case(session, gold_case_id, result.suite, case_result, now)
        await _upsert_case_result(session, case_result_id, eval_run_id, gold_case_id, case_result)
        gold_case_ids.append(gold_case_id)
        case_result_ids.append(case_result_id)

    await session.commit()
    return StoredLookupSnapshotEvalBatch(
        eval_run_id=eval_run_id,
        gold_set_case_ids=tuple(gold_case_ids),
        eval_case_result_ids=tuple(case_result_ids),
    )


async def load_latest_lookup_snapshot_eval_batch_baseline(
    session: AsyncSession,
    suite: str,
) -> LookupSnapshotEvalBatchMetrics | None:
    result = await session.execute(
        select(EvalRun)
        .where(
            EvalRun.suite == suite,
            EvalRun.model_profile == BATCH_EVAL_MODEL_PROFILE,
            EvalRun.completed_at.is_not(None),
        )
        .order_by(EvalRun.completed_at.desc(), EvalRun.created_at.desc())
        .limit(5)
    )
    for row in result.scalars().all():
        payload = _metrics_payload(getattr(row, "metrics_json"))
        if payload is None:
            continue
        metrics = batch_metrics_from_json(payload)
        if metrics is not None:
            return metrics
    return None


async def _upsert_eval_run(
    session: AsyncSession,
    eval_run_id: str,
    result: LookupSnapshotEvalBatchResult,
    now: datetime,
) -> None:
    row = await session.get(EvalRun, eval_run_id)
    metrics_json = batch_result_to_json(result)
    if row is None:
        session.add(
            EvalRun(
                id=eval_run_id,
                suite=result.suite,
                git_sha=None,
                model_profile=BATCH_EVAL_MODEL_PROFILE,
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


async def _upsert_gold_case(
    session: AsyncSession,
    gold_case_id: str,
    suite: str,
    result: LookupSnapshotEvalResult,
    now: datetime,
) -> None:
    row = await session.get(GoldSetCase, gold_case_id)
    expected_json = golden_case_to_json(result.case)
    if row is None:
        session.add(
            GoldSetCase(
                id=gold_case_id,
                suite=suite,
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
        setattr(row, "suite", suite)
        setattr(row, "jurisdiction", result.case.jurisdiction)
        setattr(row, "expected_json", expected_json)
        setattr(row, "source_urls", list(result.case.source_urls))
        setattr(row, "tags", list(result.case.tags))
        setattr(row, "updated_at", now)
    await session.flush()


async def _upsert_case_result(
    session: AsyncSession,
    case_result_id: str,
    eval_run_id: str,
    gold_case_id: str,
    result: LookupSnapshotEvalResult,
) -> None:
    row = await session.get(EvalCaseResult, case_result_id)
    diffs_json = diffs_to_json(result)
    evidence_metrics_json = _evidence_metrics_json(result)
    trajectory_metrics_json = _trajectory_metrics_json(result)
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


def _evidence_metrics_json(result: LookupSnapshotEvalResult) -> dict[str, float]:
    return {
        "citation_coverage": result.metrics.citation_coverage,
        "unsupported_claim_rate": result.metrics.unsupported_claim_rate,
        "warning_coverage": result.metrics.warning_coverage,
        "ingestion_quality_flag_coverage": result.metrics.ingestion_quality_flag_coverage,
    }


def _trajectory_metrics_json(result: LookupSnapshotEvalResult) -> dict[str, float | int]:
    return {
        "deterministic_calculation_reproducibility": (
            result.metrics.deterministic_calculation_reproducibility
        ),
        "missing_calculation_count": len(result.missing_calculations),
    }


def _metrics_payload(value: JsonValue) -> Mapping[str, JsonValue] | None:
    if not isinstance(value, dict):
        return None
    return value


def _eval_run_id(result: LookupSnapshotEvalBatchResult) -> str:
    fingerprint = "|".join(
        f"{case_result.case.case_id}:{case_result.lookup_snapshot_id}"
        for case_result in result.case_results
    )
    return str(uuid5(NAMESPACE_URL, f"plotlot:{result.suite}:batch:{fingerprint}"))


def _gold_case_id(suite: str, result: LookupSnapshotEvalResult) -> str:
    return str(uuid5(NAMESPACE_URL, f"plotlot:{suite}:case:{result.case.case_id}"))


def _case_result_id(
    suite: str,
    eval_run_id: str,
    result: LookupSnapshotEvalResult,
) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"plotlot:{suite}:batch-result:{eval_run_id}:{result.case.case_id}",
        )
    )
