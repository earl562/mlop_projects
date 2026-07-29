from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


@pytest.fixture
async def job_store() -> AsyncIterator[PostgresJobQueueStorage]:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, pool_size=8, max_overflow=8)
    lock_connection = await engine.connect()
    await lock_connection.execute(text("SELECT pg_advisory_lock(110029)"))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_provider() -> AsyncSession:
        return factory()

    store = PostgresJobQueueStorage(session_provider)
    await store.clear_for_tests()
    yield store
    await store.clear_for_tests()
    await lock_connection.execute(text("SELECT pg_advisory_unlock(110029)"))
    await lock_connection.close()
    await engine.dispose()
