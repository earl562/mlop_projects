"""Snapshot service — fetch + store + change detection + events (Phase 3).

Master spec §3/§6/§7. Takes a fetcher (injectable for tests + provider-agnostic),
produces an OrdinanceSourceSnapshot, detects change vs prior, emits the right
event (source_fetch_completed / source_unchanged / source_diff_detected /
source_fetch_failed). Idempotent: unchanged source reuses snapshot, no duplicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from plotlot.ingestion.events import HarnessEvent, IngestionEventType
from plotlot.ingestion.snapshots import OrdinanceSourceSnapshot

Fetcher = Callable[[str], Awaitable[tuple[int, str]]]


@dataclass
class SnapshotResult:
    snapshot: OrdinanceSourceSnapshot | None
    event: HarnessEvent
    changed: bool


async def fetch_and_snapshot(
    *,
    source_authority_id: str,
    source_url: str,
    fetcher: Fetcher,
    prior_snapshot: OrdinanceSourceSnapshot | None,
) -> SnapshotResult:
    """Fetch a source, store a snapshot, detect change, emit the right event.

    Args:
        fetcher: async (url) -> (http_status, content_text). Injected so the
            service is provider-agnostic (Municode / codifier / PDF / manual).
        prior_snapshot: the last stored snapshot for this authority, or None.
    """
    try:
        http_status, content = await fetcher(source_url)
    except Exception as exc:  # noqa: BLE001 — transport error
        return SnapshotResult(
            snapshot=None,
            event=HarnessEvent(
                type=IngestionEventType.SOURCE_FETCH_FAILED,
                severity="error",
                payload={
                    "authority_id": source_authority_id,
                    "source_url": source_url,
                    "error": f"{type(exc).__name__}: {exc}",
                    "stage": "fetch",
                },
            ),
            changed=False,
        )

    if http_status != 200 or not content:
        return SnapshotResult(
            snapshot=None,
            event=HarnessEvent(
                type=IngestionEventType.SOURCE_FETCH_FAILED,
                severity="error",
                payload={
                    "authority_id": source_authority_id,
                    "source_url": source_url,
                    "error": f"http_status={http_status}",
                    "stage": "fetch",
                },
            ),
            changed=False,
        )

    snapshot = OrdinanceSourceSnapshot(
        source_authority_id=source_authority_id,
        source_url=source_url,
        content=content,
        http_status=http_status,
    )

    # Change detection (master spec §6: source_unchanged / source_diff_detected).
    if prior_snapshot is not None and snapshot.is_unchanged_from(prior_snapshot):
        return SnapshotResult(
            snapshot=prior_snapshot,  # reuse — idempotent
            event=HarnessEvent(
                type=IngestionEventType.SOURCE_UNCHANGED,
                severity="info",
                payload={
                    "authority_id": source_authority_id,
                    "snapshot_id": prior_snapshot.content_hash[:16],
                    "content_hash": prior_snapshot.content_hash,
                },
            ),
            changed=False,
        )

    if prior_snapshot is not None and not snapshot.is_unchanged_from(prior_snapshot):
        return SnapshotResult(
            snapshot=snapshot,
            event=HarnessEvent(
                type=IngestionEventType.SOURCE_DIFF_DETECTED,
                severity="warning",
                payload={
                    "authority_id": source_authority_id,
                    "old_hash": prior_snapshot.content_hash,
                    "new_hash": snapshot.content_hash,
                    "changed_sections": [],
                },
            ),
            changed=True,
        )

    # First fetch (no prior).
    return SnapshotResult(
        snapshot=snapshot,
        event=HarnessEvent(
            type=IngestionEventType.SOURCE_FETCH_COMPLETED,
            severity="info",
            payload={
                "authority_id": source_authority_id,
                "snapshot_id": snapshot.content_hash[:16],
                "http_status": http_status,
                "content_hash": snapshot.content_hash,
                "bytes": len(content),
            },
        ),
        changed=True,
    )


__all__ = ["SnapshotResult", "fetch_and_snapshot"]
