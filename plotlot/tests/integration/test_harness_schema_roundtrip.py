"""Functional integration test: schema roundtrip — prove all ORM models can
write and read back through the real PostgreSQL DB. No mocks, no fixtures.

Review feedback §4.2: prove the branch feature/harness-wiring actually persists.
"""

from __future__ import annotations

import pytest
from plotlot.ingestion.events import HarnessEvent, IngestionEventType
from plotlot.ingestion.event_store import persist_event, list_events_by_ingestion_run
from plotlot.ingestion.snapshot_store import persist_snapshot, get_latest_snapshot
from plotlot.ingestion.snapshots import OrdinanceSourceSnapshot
from plotlot.ingestion.source_authorities.models import (
    AuthorityScope,
    JurisdictionSourceAuthority,
    JurisdictionType,
    OfficialStatus,
    Provider,
)
from plotlot.ingestion.source_authorities.persistence import (
    list_source_authorities,
    upsert_source_authority,
)
from plotlot.storage.db import get_session, init_db
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def _init():
    await init_db()


class TestSourceAuthorityRoundtrip:
    @pytest.mark.asyncio
    async def test_upsert_then_read_back(self):
        a = JurisdictionSourceAuthority(
            state="FL",
            county="Broward",
            municipality="Testburg",
            jurisdiction_type=JurisdictionType.MUNICIPALITY,
            authority_scope=AuthorityScope.ZONING,
            provider=Provider.MUNICODE,
            canonical_url="https://test.test",
            source_url="https://test.test",
            source_title="Testburg Zoning",
            official_status=OfficialStatus.PUBLISHER_COPY,
            legal_caveat="verify with municipality",
        )
        orm = await upsert_source_authority(a)
        assert orm.id, "must have persisted ID"
        assert orm.id.startswith("auth_")

        # Read back via list
        auths = await list_source_authorities(state="FL", authority_scope="zoning")
        found = [x for x in auths if x.municipality == "Testburg"]
        assert found, "must find persisted authority"
        assert found[0].legal_caveat == "verify with municipality"

    @pytest.mark.asyncio
    async def test_upsert_is_idempotent(self):
        a = JurisdictionSourceAuthority(
            state="FL",
            county="Broward",
            municipality="Testburg",
            jurisdiction_type=JurisdictionType.MUNICIPALITY,
            authority_scope=AuthorityScope.ZONING,
            provider=Provider.MUNICODE,
            canonical_url="https://test.test",
            source_url="https://test.test",
            source_title="Testburg Zoning",
            official_status=OfficialStatus.PUBLISHER_COPY,
            legal_caveat="verify with municipality",
        )
        first = await upsert_source_authority(a)
        second = await upsert_source_authority(a)
        assert first.id == second.id, "upsert must reuse natural key"


class TestSnapshotRoundtrip:
    @pytest.mark.asyncio
    async def _ensure_authorities(self):
        self._auth_ids = []
        for aid_name in ("auth_test_snap", "auth_test_snap2"):
            a = JurisdictionSourceAuthority(
                state="FL",
                county="Test",
                municipality=None,
                jurisdiction_type=JurisdictionType.COUNTY,
                authority_scope=AuthorityScope.ZONING,
                provider=Provider.MUNICODE,
                canonical_url=f"https://x/{aid_name}",
                source_url=f"https://x/{aid_name}",
                source_title="Test",
                official_status=OfficialStatus.PUBLISHER_COPY,
                legal_caveat="verify",
            )
            orm = await upsert_source_authority(a)
            self._auth_ids.append(orm.id)

    @pytest.mark.asyncio
    async def test_persist_then_read_back(self):
        await self._ensure_authorities()
        snap = OrdinanceSourceSnapshot(
            source_authority_id=self._auth_ids[0],
            source_url="https://x",
            content="<html>test snapshot</html>",
            http_status=200,
        )
        orm = await persist_snapshot(snap)
        assert orm.id, "must have persisted snapshot ID"
        assert orm.content_hash == snap.content_hash
        assert orm.raw_text_excerpt == snap.content[:500]

        # Read back via latest
        latest = await get_latest_snapshot(self._auth_ids[0])
        assert latest is not None
        assert latest.id == orm.id
        assert latest.content_hash == snap.content_hash

    @pytest.mark.asyncio
    async def test_latest_snapshot_returns_most_recent(self):
        await self._ensure_authorities()
        # Two snapshots → latest should be the second.
        s1 = OrdinanceSourceSnapshot(
            source_authority_id=self._auth_ids[1],
            source_url="https://x",
            content="<html>first</html>",
        )
        s2 = OrdinanceSourceSnapshot(
            source_authority_id=self._auth_ids[1],
            source_url="https://x",
            content="<html>second</html>",
        )
        await persist_snapshot(s1)
        await persist_snapshot(s2)
        latest = await get_latest_snapshot(self._auth_ids[1])
        assert latest is not None
        assert latest.content_hash == s2.content_hash, "must return most recent snapshot"


class TestEventRoundtrip:
    @pytest.mark.asyncio
    async def test_persist_then_query_by_ingestion_run(self):
        ingestion_run_id = "ingest_test_001"
        e = HarnessEvent(
            type=IngestionEventType.SOURCE_FETCH_COMPLETED,
            severity="info",
            payload={
                "authority_id": "auth_1",
                "snapshot_id": "snap_abc",
                "http_status": 200,
                "content_hash": "abc123",
                "bytes": 1234,
            },
            ingestion_run_id=ingestion_run_id,
        )
        orm = await persist_event(e)
        assert orm.id == e.id
        assert orm.type == e.type

        # Query by run
        events = await list_events_by_ingestion_run(ingestion_run_id)
        assert len(events) >= 1
        found = [x for x in events if x.id == e.id]
        assert found, f"event {e.id} must be queryable by ingestion_run_id"

    @pytest.mark.asyncio
    async def test_secret_redaction_before_persist(self):
        e = HarnessEvent(
            type=IngestionEventType.SOURCE_FETCH_COMPLETED,
            severity="info",
            payload={
                "authority_id": "auth_1",
                "snapshot_id": "snap_abc",
                "http_status": 200,
                "content_hash": "abc",
                "bytes": 1234,
                "headers": {"Authorization": "Bearer secret123"},
                "connector": {"api_key": "sk-abc"},
                "nested": [{"password": "pwd"}],
            },
        )
        orm = await persist_event(e)
        p = orm.payload
        assert p["headers"]["Authorization"] == "***REDACTED***", (
            "top-level secret must be redacted"
        )
        assert p["connector"]["api_key"] == "***REDACTED***", "nested secret must be redacted"


class TestOrdinanceChunkColumns:
    @pytest.mark.asyncio
    async def test_write_read_new_columns(self):
        """Prove the Phase 1 columns actually persist on ordinance_chunks."""
        session = await get_session()
        try:
            await session.execute(
                text("""
                INSERT INTO ordinance_chunks (municipality, county, chunk_text, chunk_index,
                    source_authority_id, snapshot_id, chunk_kind, quality_flags, table_row_key, source_page)
                VALUES ('Testville', 'TestCounty', 'test chunk', 999,
                    'auth_x', 'snap_x', 'dimensional_table', '{}'::jsonb, 'RS-8', 42)
            """)
            )
            await session.commit()
            result = await session.execute(
                text(
                    "SELECT source_authority_id, snapshot_id, chunk_kind, table_row_key, source_page FROM ordinance_chunks WHERE municipality='Testville'"
                )
            )
            row = result.one()
            assert row.source_authority_id == "auth_x"
            assert row.snapshot_id == "snap_x"
            assert row.chunk_kind == "dimensional_table"
            assert row.table_row_key == "RS-8"
            assert row.source_page == 42
        finally:
            await session.execute(
                text("DELETE FROM ordinance_chunks WHERE municipality='Testville'")
            )
            await session.commit()
            await session.close()
