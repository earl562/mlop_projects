"""Ordinance source snapshots (Phase 1 — master spec §7).

A raw fetch of a source authority, content-hashed for idempotency. Unchanged
source (same content_hash) reuses the snapshot; changed source emits
source_diff_detected. Natural key: (source_authority_id, content_hash).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _hash(content: str) -> str:
    """Deterministic SHA-256 content hash."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class OrdinanceSourceSnapshot:
    """One raw fetch of a source authority's content.

    Master spec §7. Stored BEFORE parsing (raw snapshot), so re-ingestion can
    detect changes via content_hash without re-fetching the parsed structure.
    """

    source_authority_id: str
    source_url: str
    content: str
    final_url: str | None = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    http_status: int | None = None
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    source_version: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
    # Computed in __post_init__ (deterministic).
    content_hash: str = ""
    raw_storage_url: str = ""
    raw_text_excerpt: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            object.__setattr__(self, "content_hash", _hash(self.content))
        if not self.raw_text_excerpt:
            object.__setattr__(self, "raw_text_excerpt", self.content[:500])
        if not self.final_url:
            object.__setattr__(self, "final_url", self.source_url)

    @property
    def natural_key(self) -> tuple[str, str]:
        """(source_authority_id, content_hash) — idempotency key."""
        return (self.source_authority_id, self.content_hash)

    def is_unchanged_from(self, other: "OrdinanceSourceSnapshot") -> bool:
        """Same authority + same content hash → unchanged (idempotent re-ingest)."""
        return (
            self.source_authority_id == other.source_authority_id
            and self.content_hash == other.content_hash
        )
