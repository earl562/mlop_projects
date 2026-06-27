#!/usr/bin/env python
"""Smoke: snapshot change detection with real persistence + FK."""
import asyncio
import json
import sys
from plotlot.ingestion.snapshot_service import fetch_and_snapshot
from plotlot.ingestion.snapshot_store import persist_snapshot, get_latest_snapshot
from plotlot.ingestion.source_authorities.models import (
    AuthorityScope, JurisdictionSourceAuthority, JurisdictionType, OfficialStatus, Provider,
)
from plotlot.ingestion.source_authorities.persistence import upsert_source_authority
from plotlot.storage.db import init_db


async def _fetcher_v1(_url: str) -> tuple[int, str]:
    return 200, "<html>v1</html>"


async def _fetcher_v2(_url: str) -> tuple[int, str]:
    return 200, "<html>v2</html>"


async def main():
    await init_db()

    # Create source authority first (FK constraint).
    auth = JurisdictionSourceAuthority(
        state="FL", county="Smoke", municipality=None,
        jurisdiction_type=JurisdictionType.COUNTY, authority_scope=AuthorityScope.ZONING,
        provider=Provider.MUNICODE,
        canonical_url="https://smoke.test", source_url="https://smoke.test",
        source_title="Smoke Test Authority", official_status=OfficialStatus.PUBLISHER_COPY,
        legal_caveat="verify with municipality",
    )
    orm_auth = await upsert_source_authority(auth)
    auth_id = orm_auth.id
    print(f"authority: {auth_id}", file=sys.stderr)

    # First fetch
    result1 = await fetch_and_snapshot(
        source_authority_id=auth_id, source_url="https://smoke.test",
        fetcher=_fetcher_v1, prior_snapshot=None,
    )
    if not result1.snapshot:
        print(json.dumps({"status": "fail", "error": "no snapshot"}))
    sys.exit(1)
    orm1 = await persist_snapshot(result1.snapshot)

    # Unchanged fetch
    result2 = await fetch_and_snapshot(
        source_authority_id=auth_id, source_url="https://smoke.test",
        fetcher=_fetcher_v1, prior_snapshot=result1.snapshot,
    )

    # Changed fetch
    result3 = await fetch_and_snapshot(
        source_authority_id=auth_id, source_url="https://smoke.test",
        fetcher=_fetcher_v2, prior_snapshot=result1.snapshot,
    )
    orm3 = await persist_snapshot(result3.snapshot)

    latest = await get_latest_snapshot(auth_id)
    passed = (
        result1.changed is True and result2.changed is False and result3.changed is True
        and result2.event.type == "source_unchanged"
        and result3.event.type == "source_diff_detected"
        and latest is not None and latest.id == orm3.id
    )
    print(json.dumps({
        "status": "ok" if passed else "fail",
        "first_snapshot_id": orm1.id,
        "unchanged_event": result2.event.type,
        "changed_event": result3.event.type,
        "latest_snapshot_id": latest.id if latest else None,
        "real_ids_not_hash_prefix": orm1.id.startswith("snap_"),
    }))
    sys.exit(0 if passed else 1)

asyncio.run(main())
