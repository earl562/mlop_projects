from __future__ import annotations

from dataclasses import dataclass

from plotlot.core.lookup_snapshot import LookupSnapshot
from plotlot.pipeline.lookup_snapshot_eval import LOOKUP_CORRECTNESS_SUITE, LookupSnapshotGoldenCase
from plotlot.pipeline.lookup_snapshot_eval_batch import (
    LookupSnapshotEvalBatch,
    LookupSnapshotEvalBatchCase,
    LookupSnapshotEvalBatchMetrics,
    LookupSnapshotEvalBatchResult,
    run_lookup_snapshot_eval_batch,
)
from plotlot.pipeline.lookup_snapshot_eval_batch_repository import (
    load_latest_lookup_snapshot_eval_batch_baseline,
    persist_lookup_snapshot_eval_batch,
)
from plotlot.pipeline.lookup_snapshot_golden_cases import (
    lookup_snapshot_golden_case_by_address,
    lookup_snapshot_golden_case_by_id,
)
from plotlot.pipeline.lookup_snapshot_repository import (
    PersistedLookupSnapshotRecord,
    load_lookup_snapshot_record,
)
from plotlot.pipeline.lookup_snapshot_serialization import lookup_snapshot_from_dict
from plotlot.pipeline.lookup_snapshot_store import get_lookup_snapshot
from plotlot.storage.db import get_session


@dataclass(frozen=True, slots=True)
class LookupSnapshotGoldenEvalBatchItemSpec:
    snapshot_id: str
    address: str | None = None
    case_id: str | None = None


@dataclass(frozen=True, slots=True)
class LookupSnapshotGoldenEvalBatchSpec:
    suite: str
    items: tuple[LookupSnapshotGoldenEvalBatchItemSpec, ...]
    use_latest_baseline: bool = True


@dataclass(frozen=True, slots=True)
class LookupSnapshotGoldenEvalBatchRan:
    result: LookupSnapshotEvalBatchResult


@dataclass(frozen=True, slots=True)
class LookupSnapshotGoldenEvalBatchMissingSnapshots:
    snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LookupSnapshotGoldenEvalBatchMissingGoldenCases:
    keys: tuple[str, ...]


type LookupSnapshotGoldenEvalBatchOutcome = (
    LookupSnapshotGoldenEvalBatchRan
    | LookupSnapshotGoldenEvalBatchMissingSnapshots
    | LookupSnapshotGoldenEvalBatchMissingGoldenCases
)


class GoldenEvalItemEvidenceError(ValueError):
    def __init__(self) -> None:
        super().__init__("golden eval items require address or case_id")


async def run_lookup_snapshot_golden_eval_batch(
    spec: LookupSnapshotGoldenEvalBatchSpec,
) -> LookupSnapshotGoldenEvalBatchOutcome:
    batch_cases: list[LookupSnapshotEvalBatchCase] = []
    missing_snapshot_ids: list[str] = []
    missing_golden_keys: list[str] = []

    for item in spec.items:
        snapshot = await _get_lookup_snapshot_domain(item.snapshot_id)
        if snapshot is None:
            missing_snapshot_ids.append(item.snapshot_id)
            continue

        case = _golden_case_for_item(item)
        if case is None:
            missing_golden_keys.append(_golden_item_key(item))
            continue
        batch_cases.append(LookupSnapshotEvalBatchCase(snapshot=snapshot, case=case))

    if missing_snapshot_ids:
        return LookupSnapshotGoldenEvalBatchMissingSnapshots(tuple(missing_snapshot_ids))
    if missing_golden_keys:
        return LookupSnapshotGoldenEvalBatchMissingGoldenCases(tuple(missing_golden_keys))

    baseline = (
        await _load_lookup_snapshot_eval_batch_baseline(spec.suite)
        if spec.use_latest_baseline
        else None
    )
    result = run_lookup_snapshot_eval_batch(
        LookupSnapshotEvalBatch(
            suite=spec.suite or LOOKUP_CORRECTNESS_SUITE,
            cases=tuple(batch_cases),
            baseline=baseline,
        )
    )
    await _persist_lookup_snapshot_eval_batch(result)
    return LookupSnapshotGoldenEvalBatchRan(result)


def missing_snapshot_message(snapshot_ids: tuple[str, ...]) -> str:
    return f"Lookup snapshot not found: {', '.join(snapshot_ids)}"


def missing_golden_case_message(keys: tuple[str, ...]) -> str:
    return f"Lookup golden case not found: {', '.join(keys)}"


def _golden_case_for_item(
    item: LookupSnapshotGoldenEvalBatchItemSpec,
) -> LookupSnapshotGoldenCase | None:
    if item.case_id is not None:
        by_id = lookup_snapshot_golden_case_by_id(item.case_id)
        if by_id is not None:
            return by_id
    if item.address is not None:
        return lookup_snapshot_golden_case_by_address(item.address)
    return None


def _golden_item_key(item: LookupSnapshotGoldenEvalBatchItemSpec) -> str:
    if item.case_id is not None:
        return item.case_id
    if item.address is not None:
        return item.address
    return item.snapshot_id


async def _load_lookup_snapshot_eval_batch_baseline(
    suite: str,
) -> LookupSnapshotEvalBatchMetrics | None:
    session = await get_session()
    try:
        return await load_latest_lookup_snapshot_eval_batch_baseline(session, suite)
    finally:
        await session.close()


async def _persist_lookup_snapshot_eval_batch(result: LookupSnapshotEvalBatchResult) -> None:
    session = await get_session()
    try:
        await persist_lookup_snapshot_eval_batch(session, result)
    finally:
        await session.close()


async def _get_lookup_snapshot_domain(snapshot_id: str) -> LookupSnapshot | None:
    stored = get_lookup_snapshot(snapshot_id)
    if stored is not None:
        return stored.snapshot
    persisted = await _get_persisted_lookup_snapshot(snapshot_id)
    if persisted is None:
        return None
    return lookup_snapshot_from_dict(persisted.snapshot_json)


async def _get_persisted_lookup_snapshot(
    snapshot_id: str,
) -> PersistedLookupSnapshotRecord | None:
    session = await get_session()
    try:
        return await load_lookup_snapshot_record(session, snapshot_id)
    finally:
        await session.close()
