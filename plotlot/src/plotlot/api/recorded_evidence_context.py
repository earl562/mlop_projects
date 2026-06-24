from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.models import EvidenceItem


async def recorded_evidence_ids(
    session: AsyncSession,
    evidence_ids: Iterable[str],
) -> set[str]:
    recorded_ids: set[str] = set()
    for evidence_id in evidence_ids:
        row = await session.get(EvidenceItem, evidence_id)
        if row is not None:
            recorded_ids.add(evidence_id)
    return recorded_ids
