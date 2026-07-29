from __future__ import annotations

from datetime import timedelta

from plotlot.harness.job_models import JobCreate, JobStatus, OutboxStatus
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


TENANT = "tenant_jobs_a"


async def test_completion_and_outbox_are_atomic_and_delivery_is_exactly_once(
    job_store: PostgresJobQueueStorage,
) -> None:
    created = await job_store.enqueue(
        JobCreate(
            tenant_id=TENANT,
            idempotency_key="outbox-key-000001",
            body={"subject": "synthetic-job-subject"},
            max_attempts=3,
        )
    )
    claim = await job_store.claim(
        tenant_id=TENANT,
        worker_id="worker-1",
        lease_for=timedelta(seconds=30),
    )
    assert claim is not None

    completed = await job_store.complete(
        tenant_id=TENANT,
        job_id=created.job_id,
        lease_token=claim.lease_token,
        engine_run_id="engrun_001",
        engine_revision_id="engrev_001",
        notification={"kind": "release", "run_id": "engrun_001"},
    )
    assert completed.status is JobStatus.COMPLETED
    repeated = await job_store.complete(
        tenant_id=TENANT,
        job_id=created.job_id,
        lease_token=claim.lease_token,
        engine_run_id="engrun_001",
        engine_revision_id="engrev_001",
        notification={"kind": "release", "run_id": "engrun_001"},
    )
    assert repeated.status is JobStatus.COMPLETED
    assert await job_store.count_terminal_results(TENANT, created.job_id) == 1
    assert await job_store.count_outbox(TENANT, created.job_id) == 1

    delivery = await job_store.claim_outbox(
        tenant_id=TENANT,
        worker_id="delivery-1",
        lease_for=timedelta(seconds=30),
    )
    assert delivery is not None
    receipt = await job_store.acknowledge_outbox(
        tenant_id=TENANT,
        outbox_id=delivery.outbox_id,
        lease_token=delivery.lease_token,
        provider_receipt_id="provider-receipt-1",
    )
    assert receipt.status is OutboxStatus.SENT
    retried_receipt = await job_store.acknowledge_outbox(
        tenant_id=TENANT,
        outbox_id=delivery.outbox_id,
        lease_token=delivery.lease_token,
        provider_receipt_id="provider-receipt-1",
    )
    assert retried_receipt.status is OutboxStatus.SENT
    assert await job_store.count_notification_receipts(TENANT, created.job_id) == 1
    assert (
        await job_store.claim_outbox(
            tenant_id=TENANT,
            worker_id="delivery-2",
            lease_for=timedelta(seconds=30),
        )
        is None
    )


async def test_outbox_lease_expiry_reacquires_without_duplicate_receipt(
    job_store: PostgresJobQueueStorage,
) -> None:
    created = await job_store.enqueue(
        JobCreate(
            tenant_id=TENANT,
            idempotency_key="outbox-expiry-0001",
            body={"subject": "synthetic-job-subject"},
            max_attempts=3,
        )
    )
    claim = await job_store.claim(
        tenant_id=TENANT,
        worker_id="worker-1",
        lease_for=timedelta(seconds=30),
    )
    assert claim is not None
    await job_store.complete(
        tenant_id=TENANT,
        job_id=created.job_id,
        lease_token=claim.lease_token,
        engine_run_id="engrun_002",
        engine_revision_id="engrev_002",
        notification={"kind": "release"},
    )
    first = await job_store.claim_outbox(
        tenant_id=TENANT,
        worker_id="delivery-old",
        lease_for=timedelta(milliseconds=1),
    )
    assert first is not None
    await job_store.expire_outbox_lease_for_tests(first.outbox_id)
    second = await job_store.claim_outbox(
        tenant_id=TENANT,
        worker_id="delivery-new",
        lease_for=timedelta(seconds=30),
    )
    assert second is not None
    assert second.outbox_id == first.outbox_id
    assert second.lease_token != first.lease_token
