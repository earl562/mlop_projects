"""Event persistence service — persists HarnessEvent to harness_events table.

Review feedback #8 (Phase 5). Previously HarnessEvent was only an in-memory
dataclass with no DB write path. This service provides the persistence layer:
write events, query by run, recursive redaction.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from plotlot.ingestion.events import HarnessEvent, _REDACTED_KEYS
from plotlot.storage.db import get_session
from plotlot.storage.models import HarnessEventORM


def _redact_recursive(obj: object, depth: int = 0) -> object:
    """Recursively redact sensitive keys (review feedback #9)."""
    if depth > 5:
        return obj
    if isinstance(obj, dict):
        return {
            k: (
                "***REDACTED***"
                if any(r in str(k).lower() for r in _REDACTED_KEYS)
                and not isinstance(v, (list, dict))
                else _redact_recursive(v, depth + 1)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_recursive(v, depth + 1) for v in obj]
    return obj


async def persist_event(event: HarnessEvent) -> HarnessEventORM:
    """Persist one event to the DB. Returns the ORM row after commit."""
    redacted = _redact_recursive(event.payload)
    ts: datetime = datetime.fromisoformat(event.timestamp)
    orm = HarnessEventORM(
        id=event.id,
        type=event.type,
        timestamp=ts,
        correlation_id=event.correlation_id,
        severity=event.severity,
        workspace_id=event.workspace_id,
        project_id=event.project_id,
        site_id=event.site_id,
        analysis_id=event.analysis_id,
        analysis_run_id=event.analysis_run_id,
        ingestion_run_id=event.ingestion_run_id,
        source_authority_id=event.source_authority_id,
        tool_run_id=event.tool_run_id,
        payload=redacted if isinstance(redacted, dict) else {},
    )
    session = await get_session()
    try:
        session.add(orm)
        await session.commit()
        return orm
    finally:
        await session.close()


async def persist_events(events: list[HarnessEvent]) -> list[HarnessEventORM]:
    """Persist multiple events in one transaction."""
    if not events:
        return []
    redacted_events = [
        HarnessEventORM(
            id=e.id,
            type=e.type,
            timestamp=datetime.fromisoformat(e.timestamp)
            if isinstance(e.timestamp, str)
            else e.timestamp,
            correlation_id=e.correlation_id,
            severity=e.severity,
            workspace_id=e.workspace_id,
            project_id=e.project_id,
            site_id=e.site_id,
            analysis_id=e.analysis_id,
            analysis_run_id=e.analysis_run_id,
            ingestion_run_id=e.ingestion_run_id,
            source_authority_id=e.source_authority_id,
            tool_run_id=e.tool_run_id,
            payload=_redact_recursive(e.payload)
            if isinstance(_redact_recursive(e.payload), dict)
            else {},
        )
        for e in events
    ]
    session = await get_session()
    try:
        session.add_all(redacted_events)
        await session.commit()
        return redacted_events
    finally:
        await session.close()


async def list_events_by_analysis_run(analysis_run_id: str) -> list[HarnessEventORM]:
    session = await get_session()
    try:
        result = await session.execute(
            select(HarnessEventORM)
            .where(HarnessEventORM.analysis_run_id == analysis_run_id)
            .order_by(HarnessEventORM.timestamp)
        )
        return list(result.scalars().all())
    finally:
        await session.close()


async def list_events_by_ingestion_run(ingestion_run_id: str) -> list[HarnessEventORM]:
    session = await get_session()
    try:
        result = await session.execute(
            select(HarnessEventORM)
            .where(HarnessEventORM.ingestion_run_id == ingestion_run_id)
            .order_by(HarnessEventORM.timestamp)
        )
        return list(result.scalars().all())
    finally:
        await session.close()


__all__ = [
    "list_events_by_analysis_run",
    "list_events_by_ingestion_run",
    "persist_event",
    "persist_events",
]
