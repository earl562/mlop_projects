#!/usr/bin/env python
"""Smoke: source authority roundtrip — seed + persist + read back."""
import asyncio
import json
import sys
from plotlot.ingestion.source_authorities.persistence import (
    seed_and_persist_south_florida_authorities, list_source_authorities,
)
from plotlot.storage.db import init_db

async def main():
    await init_db()
    n = await seed_and_persist_south_florida_authorities()
    auths = await list_source_authorities(state="FL")
    counties = {a.county for a in auths}
    passed = n >= 5 and "Broward" in counties and "Miami-Dade" in counties and "Palm Beach" in counties
    print(json.dumps({"status": "ok" if passed else "fail", "persisted": n, "read_back": len(auths), "counties": list(counties)}))
    sys.exit(0 if passed else 1)

asyncio.run(main())
