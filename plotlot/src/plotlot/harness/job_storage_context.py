from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import JsonValue
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.harness.job_models import JobCreate, JobId, JobRecord


class JobStorageContext(ABC):
    @abstractmethod
    async def _session(self) -> AsyncSession: ...

    @staticmethod
    @abstractmethod
    async def _set_tenant(session: AsyncSession, tenant_id: str) -> None: ...

    @abstractmethod
    async def enqueue(self, command: JobCreate) -> JobRecord: ...

    @abstractmethod
    async def _get_in_session(
        self,
        session: AsyncSession,
        tenant_id: str,
        job_id: JobId,
    ) -> RowMapping | None: ...

    @abstractmethod
    async def _event(
        self,
        session: AsyncSession,
        tenant_id: str,
        job_id: JobId,
        event_type: str,
        payload: dict[str, JsonValue],
    ) -> None: ...
