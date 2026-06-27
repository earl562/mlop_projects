#!/usr/bin/env python
"""Smoke: harness event store — persist + query + redaction."""
import asyncio
import json
import sys
import uuid
from plotlot.ingestion.events import HarnessEvent, IngestionEventType
from plotlot.ingestion.event_store import persist_event, list_events_by_ingestion_run
from plotlot.storage.db import init_db

async def main():
    await init_db()
    run_id = f"smoke_ev_{uuid.uuid4().hex[:8]}"
    e = HarnessEvent(
        type=IngestionEventType.SOURCE_FETCH_COMPLETED, severity="info",
        payload={"authority_id":"auth_1","snapshot_id":"snap_x","http_status":200,
                 "content_hash":"abc","bytes":1234, "api_key":"secret", "Authorization":"Bearer xyz"},
        ingestion_run_id=run_id,
    )
    orm = await persist_event(e)
    events = await list_events_by_ingestion_run(run_id)
    found = [x for x in events if x.id == e.id]
    p = orm.payload
    redacted = p.get("api_key") == "***REDACTED***" and p.get("Authorization") == "***REDACTED***"
    passed = len(found) > 0 and redacted
    print(json.dumps({
        "status": "ok" if passed else "fail",
        "event_id": orm.id,
        "persisted": True,
        "queryable_by_run": len(found) > 0,
        "secrets_redacted": redacted,
        "query_count": len(events),
    }))
    sys.exit(0 if passed else 1)

asyncio.run(main())
