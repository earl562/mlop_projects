"""Append-only evidence ledger service."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.models import EvidenceItem


class EvidenceService:
    """Creates and reads claim-level evidence records.

    The service is intentionally small: factual provenance belongs in a typed
    table, while higher-order report validation can build on top of it.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        claim_key: str,
        value: dict[str, Any],
        source_type: str,
        tool_name: str,
        workspace_id: str | None = None,
        project_id: str | None = None,
        site_id: str | None = None,
        analysis_run_id: str | None = None,
        source_url: str | None = None,
        source_title: str | None = None,
        confidence: str = "medium",
        retrieved_at: datetime | None = None,
    ) -> EvidenceItem:
        item = EvidenceItem(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            project_id=project_id,
            site_id=site_id,
            analysis_run_id=analysis_run_id,
            claim_key=claim_key,
            value_json=value,
            source_type=source_type,
            source_url=source_url,
            source_title=source_title,
            tool_name=tool_name,
            confidence=confidence,
            retrieved_at=retrieved_at,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def list_for_project(self, project_id: str) -> list[EvidenceItem]:
        result = await self.session.execute(
            select(EvidenceItem)
            .where(EvidenceItem.project_id == project_id)
            .order_by(EvidenceItem.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_many(self, evidence_ids: list[str]) -> list[EvidenceItem]:
        if not evidence_ids:
            return []
        result = await self.session.execute(
            select(EvidenceItem).where(EvidenceItem.id.in_(evidence_ids))
        )
        return list(result.scalars().all())
