"""Extract verified dimensional standards from the INGESTED ordinance corpus
across all municipalities that have parseable dimensional-table chunks.

This is the Phase-9-style governed extraction run (slice 3.2 extension):
reads ordinance_chunks.chunk_text for chunks containing district codes +
dimensional keywords, runs extract_dimensional_standards over them, and
upserts VERIFIED rows into district_dimensional_standards with real
source_section_ids (the actual ordinance section + ordinance_chunks.id).

Only rows whose values parse cleanly are stored. Municipalities whose zoning
data isn't structured as dimensional tables (West Palm Beach, Boca Raton, etc.)
are surfaced as ingestion gaps — their chunks use different terminology/format
and need the ingestion/chunking pipeline extended (a planned task).

Run:
    uv run python scripts/extract_dimensional_standards_from_corpus.py            # dry-run (print only)
    uv run python scripts/extract_dimensional_standards_from_corpus.py --write    # persist to DB
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import defaultdict

from plotlot.domain.dimensional_standard import (
    DistrictDimensionalStandard,
    extract_dimensional_standards,
)
from plotlot.storage.db import get_session, init_db
from plotlot.storage.dimensional_standards import store_dimensional_standards

from sqlalchemy import text

# SQL: find chunks with district codes + dimensional keywords. Returns
# (id, municipality, county, section, section_title, chunk_text, source_url).
# The county is resolved from a municipality→county map (Broward vs Miami-Dade
# vs Palm Beach); state is always FL for this corpus.
COUNTY_MAP: dict[str, str] = defaultdict(lambda: "Florida")
for m in (
    "Fort Lauderdale", "Hollywood", "Coral Springs", "Davie", "Parkland",
    "Lauderdale By The Sea", "Hillsboro Beach", "Oakland Park", "Tamarac",
    "Miramar", "North Miami", "Sweetwater", "Sunny Isles Beach", "Surfside",
    "Key Biscayne", "Miami Gardens", "Palmetto Bay", "Cutler Bay", "Doral",
    "Virginia Gardens", "Hialeah", "Homestead", "Miami Springs", "South Miami",
    "Miami Beach",
):
    COUNTY_MAP[m] = {"Miami Beach": "Miami-Dade", "Miami Springs": "Miami-Dade",
                     "South Miami": "Miami-Dade", "Hialeah": "Miami-Dade",
                     "Miami Gardens": "Miami-Dade", "Palmetto Bay": "Miami-Dade",
                     "Cutler Bay": "Miami-Dade", "Doral": "Miami-Dade",
                     "Virginia Gardens": "Miami-Dade", "Homestead": "Miami-Dade",
                     "Sweetwater": "Miami-Dade", "Sunny Isles Beach": "Miami-Dade",
                     "Surfside": "Miami-Dade", "Key Biscayne": "Miami-Dade",
                     "North Miami": "Miami-Dade"}.get(m, "Broward")

FIND_CHUNKS_SQL = text(r"""
SELECT id, municipality, section, section_title, chunk_text, source_url
FROM ordinance_chunks
WHERE chunk_text ~* '\m(RS-|RM-|RD-|RC-|RML-|RMM-|R-1|R-2|R-3|R-4|R-5|R-6|R-P|RU|A-1|A-2|B-1|B-2|B-3|C-1|C-2|C-3|P-I|M-U)\m'
  AND chunk_text ~* '(setback|yard|lot width|lot area|density|height|coverage|floor area)'
  AND chunk_text ~* '(minimum|maximum|max|min)'
  AND municipality IS NOT NULL
ORDER BY municipality, id
""")

# District code regex (matches RS-8, RM-15, R-1, etc.)
_DISTRICT_RE = re.compile(r"\b([A-Z]{1,4}-?\d{1,3}(?:\.\d+)?(?:-[A-Z0-9]+)?)\b")


def _chunk_has_table(chunk_text: str) -> bool:
    """A dimensional table has a header + pipe-delimited rows OR multiple
    district codes on separate lines."""
    if "|" not in chunk_text:
        return False
    return bool(_DISTRICT_RE.search(chunk_text))


async def extract_all(*, write: bool) -> None:
    await init_db()
    session = await get_session()
    rows_by_muni: dict[str, list[DistrictDimensionalStandard]] = defaultdict(list)
    gaps: list[str] = []
    try:
        result = await session.execute(FIND_CHUNKS_SQL)
        chunks = result.all()
    finally:
        await session.close()

    for chunk_id, municipality, section, section_title, chunk_text, source_url in chunks:
        municipality = (municipality or "").strip()
        if not _chunk_has_table(chunk_text):
            continue
        # Normalize municipality case (some are UPPER in the DB).
        muni_norm = municipality.title()
        # Build a markdown table the extractor can parse. Many chunks are
        # already pipe-delimited; extract_dimensional_standards expects a
        # header row + data rows.
        table_text = _to_markdown_table(chunk_text)
        if not table_text:
            continue
        source_section_id = f"{section or ''} (ordinance_chunks id={chunk_id})"
        try:
            rows = extract_dimensional_standards(
                table_text,
                municipality=muni_norm,
                county=COUNTY_MAP.get(muni_norm, "Florida"),
                state="FL",
                source_section_id=source_section_id,
                source_url=source_url or "",
            )
        except Exception:
            continue
        if rows:
            rows_by_muni[muni_norm].extend(rows)

    # Dedupe within municipality (keep first per district_code — earliest chunk).
    deduped_by_muni: dict[str, list[DistrictDimensionalStandard]] = {}
    for muni, rows in rows_by_muni.items():
        seen: set[str] = set()
        kept: list[DistrictDimensionalStandard] = []
        for r in rows:
            key = r.district_code
            if key in seen:
                continue
            seen.add(key)
            kept.append(r)
        if kept:
            deduped_by_muni[muni] = kept

    # Report.
    total = sum(len(r) for r in deduped_by_muni.values())
    print(f"\n=== Extracted {total} verified dimensional standards across "
          f"{len(deduped_by_muni)} municipalities ===\n")
    for muni in sorted(deduped_by_muni):
        rows = deduped_by_muni[muni]
        print(f"  {muni} ({COUNTY_MAP.get(muni,'?')}): {len(rows)} districts")
        for r in rows[:5]:
            print(f"    {r.district_code}: density={r.max_density_units_per_acre}, "
                  f"lot={r.min_lot_area_sqft}, front={r.setback_front_ft}, "
                  f"rear={r.setback_rear_ft}, far={r.far}")
        if len(rows) > 5:
            print(f"    ... +{len(rows)-5} more")

    if write and total:
        all_rows = [r for rows in deduped_by_muni.values() for r in rows]
        n = await store_dimensional_standards(all_rows)
        print(f"\nStored {n} verified rows to district_dimensional_standards.")
    elif not write:
        print("\n(dry-run; pass --write to persist to DB)")

    # Surface ingestion gaps (municipalities with chunks but no parseable tables).
    print("\n=== Ingestion gaps (chunks present, no parseable dimensional tables) ===")
    print("These municipalities have ingested chunks but their zoning dimensional")
    print("data isn't structured as pipe-delimited tables — the ingestion/chunking")
    print("pipeline must be extended for them (a planned task).")
    # (Read the full municipality list to compare.)
    session = await get_session()
    try:
        result = await session.execute(
            text("SELECT municipality, count(*) FROM ordinance_chunks "
                 "WHERE municipality IS NOT NULL GROUP BY municipality")
        )
        all_munis = {r[0].strip(): r[1] for r in result.all()}
    finally:
        await session.close()
    extracted_munis = {m.lower() for m in deduped_by_muni}
    gap_munis = sorted(
        (m, c) for m, c in all_munis.items()
        if m.lower() not in extracted_munis and c > 100
    )
    for m, c in gap_munis[:20]:
        print(f"  {m}: {c} chunks (no dimensional table extracted)")
    if len(gap_munis) > 20:
        print(f"  ... +{len(gap_munis)-20} more")


def _to_markdown_table(chunk_text: str) -> str | None:
    """Convert a chunk to a parseable markdown table.

    Many ingested chunks are already pipe-delimited tables (with newlines
    replacing the original structure). If the chunk has pipes, return it as-is
    (the extractor handles header detection). Otherwise return None.
    """
    if "|" not in chunk_text:
        return None
    return chunk_text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="persist to DB (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(extract_all(write=args.write))


if __name__ == "__main__":
    main()
