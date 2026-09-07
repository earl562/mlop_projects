"""Phase 5 TDD: ingestion pipeline — snapshot → parse → chunks → events → quality.

Master spec §5 (ingestion) + §6 (events) + §7 (chunks link to authority+snapshot)
+ §13 (test_ingest_fixture_*). Tests written BEFORE implementation.
"""

from __future__ import annotations

import pytest

from plotlot.ingestion.events import IngestionEventType
from plotlot.ingestion.parsing.tables import TableKind
from plotlot.ingestion.source_authorities.models import (
    AuthorityScope,
    JurisdictionSourceAuthority,
    JurisdictionType,
    OfficialStatus,
    Provider,
)

# Fails until pipeline.py exists (TDD).
from plotlot.ingestion.pipeline import run_ingestion


def _auth() -> JurisdictionSourceAuthority:
    return JurisdictionSourceAuthority(
        state="FL",
        county="Broward",
        municipality="Fort Lauderdale",
        jurisdiction_type=JurisdictionType.MUNICIPALITY,
        authority_scope=AuthorityScope.ZONING,
        provider=Provider.MUNICODE,
        canonical_url="https://x",
        source_url="https://x",
        source_title="Test Code",
        official_status=OfficialStatus.PUBLISHER_COPY,
        legal_caveat="verify with municipality",
    )


class TestRunIngestion:
    """Master spec §5: one authority → snapshot → sections/chunks → events."""

    @pytest.mark.asyncio
    async def test_ingests_html_with_table_preserves_chunk_kind(self):
        html = """<html><body>
        <h2>Sec. 47-5.31. RS-8 dimensional requirements</h2>
        <table><tr><th>District</th><th>Min Lot Area</th><th>Front Setback</th><th>Density</th></tr>
        <tr><td>RS-8</td><td>6000</td><td>25</td><td>8.0</td></tr></table>
        </body></html>"""

        async def fetcher(url: str) -> tuple[int, str]:
            return 200, html

        result = await run_ingestion(authority=_auth(), fetcher=fetcher, prior_snapshot=None)
        assert result.snapshot is not None
        assert result.chunks, "must produce chunks"
        # The table chunk must be classified dimensional_table (master spec §7).
        table_chunks = [
            c for c in result.chunks if c.chunk_kind == TableKind.DIMENSIONAL_TABLE.value
        ]
        assert table_chunks, "dimensional table must be classified"
        # Events: fetch_completed + parser_completed + section_indexed + chunk_created.
        types = {e.type for e in result.events}
        assert IngestionEventType.SOURCE_FETCH_COMPLETED.value in types
        assert IngestionEventType.PARSER_COMPLETED.value in types

    @pytest.mark.asyncio
    async def test_chunks_link_to_authority_and_snapshot(self):
        async def fetcher(url: str) -> tuple[int, str]:
            return 200, "<html><p>Some ordinance text here.</p></html>"

        result = await run_ingestion(authority=_auth(), fetcher=fetcher, prior_snapshot=None)
        for c in result.chunks:
            assert c.source_authority_id == _auth().id
            assert c.snapshot_id == result.snapshot.content_hash[:16] if result.snapshot else True

    @pytest.mark.asyncio
    async def test_idempotent_unchanged_source_no_duplicate_chunks(self):
        html = "<html><p>Same content.</p></html>"

        async def fetcher(url: str) -> tuple[int, str]:
            return 200, html

        prior_snapshot = None
        first = await run_ingestion(
            authority=_auth(), fetcher=fetcher, prior_snapshot=prior_snapshot
        )
        # re-ingest with the now-stored snapshot as prior — must be unchanged.
        second = await run_ingestion(
            authority=_auth(), fetcher=fetcher, prior_snapshot=first.snapshot
        )
        assert second.changed is False
        assert not second.chunks  # no new chunks on unchanged source
        types = {e.type for e in second.events}
        assert IngestionEventType.SOURCE_UNCHANGED.value in types

    @pytest.mark.asyncio
    async def test_failed_fetch_emits_failure_no_chunks(self):
        async def fetcher(url: str) -> tuple[int, str]:
            return 503, ""

        result = await run_ingestion(authority=_auth(), fetcher=fetcher, prior_snapshot=None)
        assert result.snapshot is None
        assert not result.chunks
        types = {e.type for e in result.events}
        assert IngestionEventType.SOURCE_FETCH_FAILED.value in types

    @pytest.mark.asyncio
    async def test_quality_score_computed(self):
        async def fetcher(url: str) -> tuple[int, str]:
            return (
                200,
                "<html><table><tr><th>District</th><th>Density</th></tr><tr><td>RS-8</td><td>8.0</td></tr></table></html>",
            )

        result = await run_ingestion(authority=_auth(), fetcher=fetcher, prior_snapshot=None)
        assert result.quality_score is not None
        assert 0.0 <= result.quality_score <= 1.0
        assert IngestionEventType.JURISDICTION_QUALITY_SCORED.value in {
            e.type for e in result.events
        }
