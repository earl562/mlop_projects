"""Migration: Clean literal \\n and \\r from zone_codes[] in ordinance_chunks.

The chunker's _extract_zone_codes stored zone codes like "BR\\n1" instead of
"BR1" because the regex captured \\n as whitespace but the sanitization only
replaced spaces. This migration strips all whitespace from existing zone_codes
entries and is safe to re-run (idempotent).

Usage:
    uv run python scripts/migrate_clean_zone_codes.py          # dry-run
    uv run python scripts/migrate_clean_zone_codes.py --apply   # apply changes
"""

import argparse
import asyncio
import os
import sys
import asyncpg

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def main(apply: bool):
    conn = await asyncpg.connect(DATABASE_URL)

    # Count rows with whitespace in zone_codes
    dirty_count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM ordinance_chunks
        WHERE zone_codes IS NOT NULL
        AND array_to_string(zone_codes, '') ~ '[\\s]'
        """
    )

    total_with_zones = await conn.fetchval(
        """
        SELECT COUNT(*) FROM ordinance_chunks
        WHERE zone_codes IS NOT NULL AND array_length(zone_codes, 1) > 0
        """
    )

    print(f"Total chunks with zone_codes: {total_with_zones}")
    print(f"Chunks with whitespace in zone_codes: {dirty_count}")

    if dirty_count == 0:
        print("No cleanup needed — all zone_codes are already clean.")
        await conn.close()
        return

    # Show sample of dirty zone codes
    samples = await conn.fetch(
        """
        SELECT municipality, zone_codes
        FROM ordinance_chunks
        WHERE zone_codes IS NOT NULL
        AND array_to_string(zone_codes, '') ~ '[\\s]'
        LIMIT 10
        """
    )
    print("\nSample dirty zone_codes:")
    for s in samples:
        dirty_codes = [zc for zc in s["zone_codes"] if any(c.isspace() for c in zc)]
        if dirty_codes:
            print(f"  {s['municipality']}: {dirty_codes}")

    if not apply:
        print("\n[DRY RUN] No changes made. Run with --apply to clean zone_codes.")
        await conn.close()
        return

    # Apply: strip all whitespace from each zone_code in the array
    print("\nApplying migration...")
    updated = await conn.fetchval(
        """
        WITH cleaned AS (
            SELECT id,
                   (
                       SELECT array_agg(
                           regexp_replace(zone_code, '\\s', '', 'g')
                       )
                       FROM unnest(zone_codes) AS zone_code
                   ) AS new_zone_codes
            FROM ordinance_chunks
            WHERE zone_codes IS NOT NULL
            AND array_to_string(zone_codes, '') ~ '[\\s]'
        )
        UPDATE ordinance_chunks
        SET zone_codes = cleaned.new_zone_codes
        FROM cleaned
        WHERE ordinance_chunks.id = cleaned.id
        RETURNING ordinance_chunks.id
        """
    )

    print(f"Updated {updated} rows.")

    # Verify
    remaining = await conn.fetchval(
        """
        SELECT COUNT(*) FROM ordinance_chunks
        WHERE zone_codes IS NOT NULL
        AND array_to_string(zone_codes, '') ~ '[\\s]'
        """
    )
    print(f"Remaining dirty zone_codes after migration: {remaining}")

    # Show sample of cleaned zone codes for Lake Worth Beach
    print("\nLake Worth Beach zone codes after migration:")
    rows = await conn.fetch(
        """
        SELECT DISTINCT zone_code
        FROM ordinance_chunks, unnest(zone_codes) AS zone_code
        WHERE municipality ILIKE '%Lake Worth Beach%'
        AND zone_code LIKE 'BR%'
        LIMIT 10
        """
    )
    for r in rows:
        print(f"  {repr(r['zone_code'])}")

    await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
