from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.pipeline.lookup_snapshot_eval_batch_repository import BATCH_EVAL_MODEL_PROFILE
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.models import EvalRun

BATCH_HISTORY_LIMIT_MAX: Final = 100
BATCH_HISTORY_METRIC_KEYS: Final = (
    "pass_rate",
    "case_count",
    "passed_count",
    "failed_count",
    "field_value_accuracy",
    "display_state_accuracy",
    "citation_coverage",
    "warning_coverage",
    "ingestion_quality_flag_coverage",
    "deterministic_calculation_reproducibility",
    "unsupported_claim_rate",
)
REQUIRED_BATCH_HISTORY_METRIC_KEYS: Final = tuple(
    key for key in BATCH_HISTORY_METRIC_KEYS if key != "ingestion_quality_flag_coverage"
)


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvalBatchHistoryRecord:
    eval_run_id: str
    suite: str
    status: str
    created_at: datetime | None
    completed_at: datetime | None
    payload: dict[str, JsonValue]


async def load_lookup_snapshot_eval_batch_history(
    session: AsyncSession,
    *,
    suite: str,
    limit: int = 20,
) -> tuple[LookupSnapshotEvalBatchHistoryRecord, ...]:
    result = await session.execute(
        select(EvalRun)
        .where(
            EvalRun.suite == suite,
            EvalRun.model_profile == BATCH_EVAL_MODEL_PROFILE,
            EvalRun.completed_at.is_not(None),
        )
        .order_by(EvalRun.completed_at.desc(), EvalRun.created_at.desc())
        .limit(_clamped_limit(limit))
    )
    records: list[LookupSnapshotEvalBatchHistoryRecord] = []
    for row in result.scalars().all():
        record = _history_record(row)
        if record is not None:
            records.append(record)
    return tuple(records)


def _history_record(row: EvalRun) -> LookupSnapshotEvalBatchHistoryRecord | None:
    eval_run_id = _str_attr(row, "id")
    suite = _str_attr(row, "suite")
    status = _str_attr(row, "status")
    payload = _json_object(getattr(row, "metrics_json"))
    if (
        eval_run_id is None
        or suite is None
        or status is None
        or payload is None
        or not _has_batch_metrics(payload)
    ):
        return None
    return LookupSnapshotEvalBatchHistoryRecord(
        eval_run_id=eval_run_id,
        suite=suite,
        status=status,
        created_at=_datetime_attr(row, "created_at"),
        completed_at=_datetime_attr(row, "completed_at"),
        payload=payload,
    )


def _json_object(value: JsonValue) -> dict[str, JsonValue] | None:
    if not isinstance(value, dict):
        return None
    payload: dict[str, JsonValue] = {}
    for key, item in value.items():
        if isinstance(key, str):
            payload[key] = item
    return payload


def _has_batch_metrics(payload: Mapping[str, JsonValue]) -> bool:
    return all(_has_number(payload, key) for key in REQUIRED_BATCH_HISTORY_METRIC_KEYS)


def _has_number(payload: Mapping[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    return not isinstance(value, bool) and isinstance(value, int | float)


def _clamped_limit(limit: int) -> int:
    return max(1, min(limit, BATCH_HISTORY_LIMIT_MAX))


def _str_attr(row: EvalRun, name: str) -> str | None:
    value = getattr(row, name)
    if isinstance(value, str):
        return value
    return None


def _datetime_attr(row: EvalRun, name: str) -> datetime | None:
    value = getattr(row, name)
    if isinstance(value, datetime):
        return value
    return None
