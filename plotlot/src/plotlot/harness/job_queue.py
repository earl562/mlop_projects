from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from pydantic import JsonValue

from plotlot.harness.job_models import JobRecord, LeaseInvariantError
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage
from plotlot.harness.run_persistence import persist_engine_result
from plotlot.storage.db import get_session


@dataclass(frozen=True, slots=True)
class EngineResult:
    engine_run_id: str
    engine_revision_id: str
    notification: dict[str, JsonValue]


class EngineRunner(Protocol):
    async def run(
        self,
        body: dict[str, JsonValue],
        idempotency_key: str,
    ) -> EngineResult: ...


class HarnessJobQueue:
    def __init__(
        self,
        storage: PostgresJobQueueStorage,
        engine: EngineRunner,
    ) -> None:
        self._storage = storage
        self._engine = engine

    async def run_once(
        self,
        *,
        tenant_id: str,
        worker_id: str,
        lease_for: timedelta,
    ) -> JobRecord | None:
        leased = await self._storage.claim(
            tenant_id=tenant_id,
            worker_id=worker_id,
            lease_for=lease_for,
        )
        if leased is None:
            return None
        if leased.lease_token is None:
            raise LeaseInvariantError("claimed job has no fencing token")
        running = await self._storage.mark_started(
            tenant_id,
            leased.job_id,
            leased.lease_token,
        )
        result = await self._engine.run(running.body, running.idempotency_key)
        return await persist_engine_result(
            self._storage,
            running,
            engine_run_id=result.engine_run_id,
            engine_revision_id=result.engine_revision_id,
            notification=result.notification,
        )


def default_harness_job_storage() -> PostgresJobQueueStorage:
    return PostgresJobQueueStorage(get_session)
