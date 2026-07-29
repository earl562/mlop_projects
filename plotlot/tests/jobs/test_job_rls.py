from __future__ import annotations

import os
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from plotlot.harness.job_models import JobCreate
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


async def test_application_role_cannot_observe_or_insert_another_tenant(
    job_store: PostgresJobQueueStorage,
) -> None:
    await job_store.enqueue(
        JobCreate(
            tenant_id="tenant_jobs_a",
            idempotency_key="rls-tenant-a-000001",
            body={"subject": "tenant-a-redacted"},
            max_attempts=3,
        )
    )
    await job_store.enqueue(
        JobCreate(
            tenant_id="tenant_jobs_b",
            idempotency_key="rls-tenant-b-000001",
            body={"subject": "tenant-b-redacted"},
            max_attempts=3,
        )
    )
    engine = create_async_engine(os.environ["JOB_APP_DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_provider() -> AsyncSession:
        return factory()

    app_store = PostgresJobQueueStorage(session_provider)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('app.tenant_id', 'tenant_jobs_a', true)")
            )
            visible = await connection.scalar(text("SELECT count(*) FROM plotlot.jobs"))
            assert visible == 1
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(
                    text("SELECT set_config('app.tenant_id', 'tenant_jobs_a', true)")
                )
                await connection.execute(
                    text(
                        """INSERT INTO plotlot.jobs
                        (tenant_id, job_id, idempotency_key, body_sha256, body, max_attempts)
                        VALUES ('tenant_jobs_b', '00000000-0000-0000-0000-000000000099',
                        'cross-tenant-attempt',
                        repeat('0', 64), '{}', 3)"""
                    )
                )
        claimed = await app_store.claim(
            tenant_id="tenant_jobs_a",
            worker_id="rls-worker",
            lease_for=timedelta(seconds=30),
        )
        assert claimed is not None
        assert claimed.lease_token is not None
        running = await app_store.mark_started(
            "tenant_jobs_a",
            claimed.job_id,
            claimed.lease_token,
        )
        assert running.lease_token is not None
        await app_store.complete(
            tenant_id="tenant_jobs_a",
            job_id=running.job_id,
            lease_token=running.lease_token,
            engine_run_id="engrun_rls",
            engine_revision_id="engrev_rls",
            notification={"kind": "release"},
        )
        assert (
            await job_store.count_terminal_results(
                "tenant_jobs_a",
                claimed.job_id,
            )
            == 1
        )
    finally:
        await engine.dispose()
