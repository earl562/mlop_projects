from __future__ import annotations

from datetime import timedelta

import anyio
import pytest

from plotlot.harness.job_models import (
    IdempotencyConflictError,
    InvalidJobTransitionError,
    JobCreate,
    JobStatus,
)
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


TENANT_A = "tenant_jobs_a"
TENANT_B = "tenant_jobs_b"


def command(tenant: str, key: str, subject: str = "synthetic-job-subject") -> JobCreate:
    return JobCreate(
        tenant_id=tenant,
        idempotency_key=key,
        body={"subject": subject, "analysis_type": "acquisition"},
        max_attempts=3,
    )


async def test_one_hundred_same_body_duplicates_return_one_tenant_job(
    job_store: PostgresJobQueueStorage,
) -> None:
    jobs = []

    async def submit() -> None:
        jobs.append(await job_store.enqueue(command(TENANT_A, "duplicate-key-0001")))

    async with anyio.create_task_group() as group:
        for _ in range(100):
            group.start_soon(submit)

    assert len({job.job_id for job in jobs}) == 1
    assert await job_store.count_jobs(TENANT_A) == 1
    claim = await job_store.claim(
        tenant_id=TENANT_A,
        worker_id="duplicate-worker",
        lease_for=timedelta(seconds=30),
    )
    assert claim is not None
    assert claim.lease_token is not None
    await job_store.complete(
        tenant_id=TENANT_A,
        job_id=claim.job_id,
        lease_token=claim.lease_token,
        engine_run_id="engrun_duplicate",
        engine_revision_id="engrev_duplicate",
        notification={"kind": "release"},
    )
    assert await job_store.count_terminal_results(TENANT_A, claim.job_id) == 1
    assert await job_store.count_outbox(TENANT_A, claim.job_id) == 1


async def test_idempotency_is_tenant_scoped_and_changed_body_conflicts(
    job_store: PostgresJobQueueStorage,
) -> None:
    first = await job_store.enqueue(command(TENANT_A, "shared-key-0000001"))
    other_tenant = await job_store.enqueue(command(TENANT_B, "shared-key-0000001"))
    assert first.job_id != other_tenant.job_id

    with pytest.raises(IdempotencyConflictError):
        await job_store.enqueue(
            command(TENANT_A, "shared-key-0000001", subject="changed-synthetic-subject")
        )


async def test_cancel_fences_completion_and_replay_preserves_causality(
    job_store: PostgresJobQueueStorage,
) -> None:
    original = await job_store.enqueue(command(TENANT_A, "cancel-key-000001"))
    claim = await job_store.claim(
        tenant_id=TENANT_A,
        worker_id="worker-1",
        lease_for=timedelta(seconds=30),
    )
    assert claim is not None
    cancelled = await job_store.cancel(
        tenant_id=TENANT_A,
        job_id=original.job_id,
        actor_id="analyst-1",
        reason="superseded",
    )
    assert cancelled.status is JobStatus.CANCELLED
    with pytest.raises(InvalidJobTransitionError):
        await job_store.complete(
            tenant_id=TENANT_A,
            job_id=claim.job_id,
            lease_token=claim.lease_token,
            engine_run_id="engrun_cancelled",
            engine_revision_id="engrev_cancelled",
            notification={"kind": "release"},
        )

    replay = await job_store.replay(
        tenant_id=TENANT_A,
        job_id=original.job_id,
        idempotency_key="replay-key-000001",
        actor_id="analyst-1",
    )
    assert replay.replay_of_job_id == original.job_id
    events = await job_store.events(
        tenant_id=TENANT_A,
        job_id=replay.job_id,
        after_cursor=0,
        limit=100,
    )
    assert [event.event_type for event in events][-1] == "job.replayed"
    assert all(left.cursor < right.cursor for left, right in zip(events, events[1:], strict=False))


async def test_cancel_and_approved_release_race_has_one_linearized_terminal(
    job_store: PostgresJobQueueStorage,
) -> None:
    created = await job_store.enqueue(command(TENANT_A, "approval-race-000001"))
    claim = await job_store.claim(
        tenant_id=TENANT_A,
        worker_id="race-worker",
        lease_for=timedelta(seconds=30),
    )
    assert claim is not None
    assert claim.lease_token is not None
    outcomes: list[str] = []

    async def cancel() -> None:
        try:
            await job_store.cancel(
                tenant_id=TENANT_A,
                job_id=created.job_id,
                actor_id="analyst-1",
                reason="race",
            )
            outcomes.append("cancelled")
        except InvalidJobTransitionError:
            outcomes.append("cancel-conflict")

    async def approve_and_release() -> None:
        try:
            await job_store.complete(
                tenant_id=TENANT_A,
                job_id=claim.job_id,
                lease_token=claim.lease_token,
                engine_run_id="engrun_approval_race",
                engine_revision_id="engrev_approval_race",
                notification={"kind": "approved-release"},
            )
            outcomes.append("released")
        except InvalidJobTransitionError:
            outcomes.append("release-conflict")

    async with anyio.create_task_group() as group:
        group.start_soon(cancel)
        group.start_soon(approve_and_release)

    final = await job_store.get(TENANT_A, created.job_id)
    assert set(outcomes) in (
        {"cancelled", "release-conflict"},
        {"released", "cancel-conflict"},
    )
    if final.status is JobStatus.COMPLETED:
        assert await job_store.count_terminal_results(TENANT_A, created.job_id) == 1
        assert await job_store.count_outbox(TENANT_A, created.job_id) == 1
    else:
        assert final.status is JobStatus.CANCELLED
        assert await job_store.count_terminal_results(TENANT_A, created.job_id) == 0
        assert await job_store.count_outbox(TENANT_A, created.job_id) == 0


async def test_cancel_and_retry_race_never_revives_cancelled_work(
    job_store: PostgresJobQueueStorage,
) -> None:
    created = await job_store.enqueue(command(TENANT_A, "retry-race-00000001"))
    claim = await job_store.claim(
        tenant_id=TENANT_A,
        worker_id="retry-race-worker",
        lease_for=timedelta(seconds=30),
    )
    assert claim is not None
    assert claim.lease_token is not None

    async def retry() -> None:
        try:
            await job_store.fail(
                TENANT_A,
                claim.job_id,
                claim.lease_token,
                "transient-race",
            )
        except InvalidJobTransitionError:
            return

    async def cancel() -> None:
        await job_store.cancel(
            tenant_id=TENANT_A,
            job_id=created.job_id,
            actor_id="analyst-1",
            reason="cancel-retry-race",
        )

    async with anyio.create_task_group() as group:
        group.start_soon(retry)
        group.start_soon(cancel)

    final = await job_store.get(TENANT_A, created.job_id)
    assert final.status is JobStatus.CANCELLED
    assert (
        await job_store.claim(
            tenant_id=TENANT_A,
            worker_id="revival-probe",
            lease_for=timedelta(seconds=30),
        )
        is None
    )
