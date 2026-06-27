#!/usr/bin/env python
"""Smoke: dimensional standard live DB lookup (no fixture fallback)."""
import asyncio
import json
import sys
from plotlot.storage.dimensional_standards import get_dimensional_standard
from plotlot.storage.db import init_db

async def main():
    await init_db()
    got = await get_dimensional_standard("Fort Lauderdale", "RS-8", allow_fixture_fallback=False)
    if got is None:
        print(json.dumps({"status": "fail", "error": "verified FTL/RS-8 not found in live DB"}))
    sys.exit(1)
    passed = (
        got.verification_status.value == "verified"
        and got.max_density_units_per_acre == 8.0
        and got.setback_rear_ft == 15
        and got.is_verified_fact_source() is True
    )
    # Also check staged row
    staged = await get_dimensional_standard("Miami", "R-4", allow_fixture_fallback=False)
    staged_correct = staged is None or staged.is_verified_fact_source() is False
    print(json.dumps({
        "status": "ok" if passed and staged_correct else "fail",
        "ftl_rs8_density": got.max_density_units_per_acre,
        "ftl_rs8_rear_setback": got.setback_rear_ft,
        "ftl_rs8_verified": got.is_verified_fact_source(),
        "verification_status": got.verification_status.value,
        "staged_not_verified": staged_correct,
        "fixture_fallback_disabled": True,
    }))
    sys.exit(0 if passed and staged_correct else 1)

asyncio.run(main())
