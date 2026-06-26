"""Backfill ordinance_sections from ordinance_chunks for a municipality (Slice 3.5).

The structural index (ordinance_sections) was added in Slice 3.1, but chunks
ingested BEFORE that slice didn't populate path/cross_refs/section_type (those
fields live on ordinance_sections, not ordinance_chunks). This script rebuilds
the structural index for an already-ingested municipality by deriving:

  * section_type — from section_title (dimensional_table / schedule / list /
    intent / definition / procedural / general)
  * path — from the municode_node_id (segmented into a hierarchy array)
  * cross_refs — from zone_codes referenced in the section's chunks (district
    codes that appear in the section text, indicating cross-references to
    other zoning districts)

Idempotent: upserts on the (municipality, node_id) natural key.

Run:
    uv run python scripts/backfill_ordinance_sections.py "Fort Lauderdale"
    uv run python scripts/backfill_ordinance_sections.py --all            # all municipalities with chunks
"""

from __future__ import annotations

import argparse
import asyncio
import re

from sqlalchemy import text

from plotlot.storage.db import get_session, init_db
from plotlot.storage.models import OrdinanceSection

# Municode node_id is a compressed path string. Segments are identified by
# known prefixes: CH (chapter), ART (article), DIV (division), S (section).
# We split on these boundaries to recover the hierarchy.
_NODE_SEGMENTS = re.compile(
    r"(CH\d+[A-Z]*|ART[A-Z]*|DIV[A-Z]*|S\d[\d.-]*[A-Z]*|"
    r"UNLA[A-Z]*|ORDO[A-Z]*|COOR[A-Z]*|SCWDIRE[A-Z]*|"
    r"SCH[A-Z]*|APP[A-Z]*|TIT[A-Z]*)"
)

# Section-type classification from section_title keywords.
_SECTION_TYPES = [
    ("dimensional_table", re.compile(r"\b(table of dimensional|dimensional requirement|schedule of (district|regulation)|bulk regulation)\b", re.I)),
    ("schedule", re.compile(r"\b(schedule|table)\b", re.I)),
    ("definition", re.compile(r"\b(definition|abbreviat)\b", re.I)),
    ("intent", re.compile(r"\b(intent and purpose|purpose)\b", re.I)),
    ("list", re.compile(r"\b(listing|list of)\b", re.I)),
    ("procedural", re.compile(r"\b(procedure|application|permit|hearing|review|approval)\b", re.I)),
    ("general", re.compile(r"\b(generally|scope|applicab)\b", re.I)),
]


def _classify_section_type(section_title: str, chunk_text: str | None = None) -> str:
    """Classify a section by its title (+ text) into a structural type."""
    haystack = section_title or ""
    for stype, pattern in _SECTION_TYPES:
        if pattern.search(haystack):
            return stype
    # Fallback: if the chunk text has a dimensional table (pipes + district
    # codes + setback keywords), classify as dimensional_table.
    if chunk_text and "|" in chunk_text and re.search(r"\b(setback|lot area|density|FAR)\b", chunk_text, re.I):
        return "dimensional_table"
    return "other"


def _derive_path(node_id: str) -> list[str]:
    """Derive a hierarchy path from a municode node_id.

    Municode node_ids are compressed path strings. We segment on known
    structural prefixes (CH, ART, DIV, S) to recover the hierarchy. The
    fallback (no recognizable segments) is a single-element path [node_id].
    """
    if not node_id:
        return []
    segments = _NODE_SEGMENTS.findall(node_id)
    if not segments:
        return [node_id]
    # Build cumulative path (each segment is a deeper level).
    path: list[str] = []
    for seg in segments:
        path.append(seg)
    return path


def _derive_cross_refs(zone_codes: list[str]) -> list[str]:
    """Cross-references = distinct district codes referenced in the section."""
    if not zone_codes:
        return []
    return sorted({c for c in zone_codes if c})


async def backfill_municipality(municipality: str) -> int:
    """Backfill ordinance_sections for one municipality. Returns rows written."""
    await init_db()
    session = await get_session()
    try:
        # Gather all chunks for this municipality, grouped by node_id.
        sql = text("""
            SELECT municode_node_id, municipality, county,
                   MIN(section) AS section_number,
                   MIN(section_title) AS section_title,
                   array_remove(array_agg(DISTINCT unnested_code), NULL) AS all_zone_codes,
                   MIN(chunk_text) AS sample_chunk_text,
                   MIN(source_url) AS source_url,
                   MIN(scraped_at) AS scraped_at
            FROM ordinance_chunks,
                 LATERAL unnest(COALESCE(zone_codes, ARRAY[]::varchar[])) AS unnested_code
            WHERE municipality = :muni AND municode_node_id IS NOT NULL
            GROUP BY municode_node_id, municipality, county
        """)
        result = await session.execute(sql, {"muni": municipality})
        rows = result.all()
        if not rows:
            print(f"  {municipality}: no chunks with node_id; skipping.")
            return 0

        # Flatten zone_codes (ARRAY_AGG of arrays → flatten).
        section_dicts = []
        for r in rows:
            node_id, muni, county, sec_num, sec_title, zone_arrays, sample_text, source_url, scraped = r
            all_codes: list[str] = []
            if zone_arrays:
                all_codes.extend(zone_arrays)
            section_type = _classify_section_type(sec_title or "", sample_text)
            path = _derive_path(node_id)
            xrefs = _derive_cross_refs(all_codes)
            section_dicts.append({
                "municipality": muni,
                "county": county or "",
                "state": "FL",
                "node_id": node_id,
                "heading": sec_title,
                "section_number": sec_num,
                "section_title": sec_title,
                "section_type": section_type,
                "path": path,
                "cross_refs": xrefs,
                "source_url": source_url or "",
                "scraped_at": scraped,
            })

        # Upsert via raw SQL (the ORM upsert with arrays needs pg_insert).
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(OrdinanceSection).values(section_dicts)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_section_natural_key",
            set_={
                "heading": stmt.excluded.heading,
                "section_number": stmt.excluded.section_number,
                "section_title": stmt.excluded.section_title,
                "section_type": stmt.excluded.section_type,
                "path": stmt.excluded.path,
                "cross_refs": stmt.excluded.cross_refs,
                "source_url": stmt.excluded.source_url,
                "scraped_at": stmt.excluded.scraped_at,
            },
        )
        await session.execute(stmt)
        await session.commit()
        type_counts: dict[str, int] = {}
        for s in section_dicts:
            type_counts[s["section_type"]] = type_counts.get(s["section_type"], 0) + 1
        print(f"  {municipality}: {len(section_dicts)} sections indexed. "
              f"types={type_counts}")
        return len(section_dicts)
    finally:
        await session.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("municipality", nargs="?", default=None,
                        help="municipality to backfill (or --all)")
    parser.add_argument("--all", action="store_true",
                        help="backfill all municipalities with chunks")
    args = parser.parse_args()
    if args.all:
        await init_db()
        session = await get_session()
        try:
            result = await session.execute(
                text("SELECT DISTINCT municipality FROM ordinance_chunks "
                     "WHERE municipality IS NOT NULL ORDER BY municipality")
            )
            munis = [r[0] for r in result.all()]
        finally:
            await session.close()
        total = 0
        for m in munis:
            total += await backfill_municipality(m)
        print(f"\nBackfilled {total} sections across {len(munis)} municipalities.")
    elif args.municipality:
        await backfill_municipality(args.municipality)
    else:
        parser.error("pass a municipality or --all")


if __name__ == "__main__":
    asyncio.run(main())
