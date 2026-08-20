"""Phase 3 TDD: snapshot layer — content hashing, change detection, events.

Master spec §7 (snapshots) + §6 (events: source_unchanged / source_diff_detected).
Tests written BEFORE implementation.
"""

from __future__ import annotations

import pytest

from plotlot.ingestion.events import IngestionEventType
from plotlot.ingestion.snapshots import OrdinanceSourceSnapshot

# Fails until snapshot_service exists (TDD).
from plotlot.ingestion.snapshot_service import (
    fetch_and_snapshot,
)


class TestSnapshotHashing:
    """Master spec §7: deterministic content hash, idempotency."""

    def test_unchanged_content_reuses_snapshot(self):
        s1 = OrdinanceSourceSnapshot(
            source_authority_id="a1", source_url="https://x", content="same"
        )
        s2 = OrdinanceSourceSnapshot(
            source_authority_id="a1", source_url="https://x", content="same"
        )
        assert s1.is_unchanged_from(s2)

    def test_changed_content_different_hash(self):
        s1 = OrdinanceSourceSnapshot(source_authority_id="a1", source_url="https://x", content="A")
        s2 = OrdinanceSourceSnapshot(source_authority_id="a1", source_url="https://x", content="B")
        assert not s1.is_unchanged_from(s2)


class TestFetchAndSnapshot:
    """Master spec §3/§6: fetch → snapshot → detect change → emit event."""

    @pytest.mark.asyncio
    async def test_first_fetch_stores_snapshot_and_emits_completed(self):
        # Fetcher returns content; service stores snapshot + emits source_fetch_completed.
        async def fetcher(url: str) -> tuple[int, str]:
            return 200, "<html>first</html>"

        result = await fetch_and_snapshot(
            source_authority_id="auth_1",
            source_url="https://x",
            fetcher=fetcher,
            prior_snapshot=None,
        )
        assert result.snapshot is not None
        assert result.snapshot.content_hash  # stored
        assert result.event.type == IngestionEventType.SOURCE_FETCH_COMPLETED.value
        assert result.event.payload["content_hash"] == result.snapshot.content_hash
        assert result.changed is True

    @pytest.mark.asyncio
    async def test_unchanged_source_emits_source_unchanged_no_new_snapshot(self):
        async def fetcher(url: str) -> tuple[int, str]:
            return 200, "<html>same</html>"

        prior = OrdinanceSourceSnapshot(
            source_authority_id="auth_1", source_url="https://x", content="<html>same</html>"
        )
        result = await fetch_and_snapshot(
            source_authority_id="auth_1",
            source_url="https://x",
            fetcher=fetcher,
            prior_snapshot=prior,
        )
        # Idempotent: no new snapshot, source_unchanged event.
        assert result.snapshot is prior or result.snapshot.content_hash == prior.content_hash
        assert result.event.type == IngestionEventType.SOURCE_UNCHANGED.value
        assert result.changed is False

    @pytest.mark.asyncio
    async def test_changed_source_emits_source_diff_detected(self):
        async def fetcher(url: str) -> tuple[int, str]:
            return 200, "<html>new content</html>"

        prior = OrdinanceSourceSnapshot(
            source_authority_id="auth_1", source_url="https://x", content="<html>old</html>"
        )
        result = await fetch_and_snapshot(
            source_authority_id="auth_1",
            source_url="https://x",
            fetcher=fetcher,
            prior_snapshot=prior,
        )
        assert result.changed is True
        assert result.event.type == IngestionEventType.SOURCE_DIFF_DETECTED.value
        assert result.event.payload["old_hash"] == prior.content_hash
        assert result.event.payload["new_hash"] == result.snapshot.content_hash

    @pytest.mark.asyncio
    async def test_failed_fetch_emits_source_fetch_failed(self):
        async def fetcher(url: str) -> tuple[int, str]:
            return 503, ""

        result = await fetch_and_snapshot(
            source_authority_id="auth_1",
            source_url="https://x",
            fetcher=fetcher,
            prior_snapshot=None,
        )
        assert result.snapshot is None
        assert result.event.type == IngestionEventType.SOURCE_FETCH_FAILED.value
        assert result.event.severity == "error"
