"""Diagnose why RM-3-7 density comes back PROVISIONAL instead of firm 6 units.

Runs the REAL pipeline retrieval + verification against your Neon DB so what you
see is exactly what the extractor sees. Answers three questions in order:

  1. Is San Diego actually ingested, and is the §131.0406 RM-density chunk
     ("1 dwelling unit for each 1,000 square feet of lot area") in the DB at all?
  2. Does hybrid_search RETRIEVE that chunk for the RM-3-7 density query
     (and at what rank)?
  3. Does extraction_verify GROUND the 1,000 sqft/DU value from the retrieved
     text — i.e. would the offer be firm (grounded) or provisional (not)?

Run from the plotlot/ dir with your env loaded:

    DATABASE_URL=...  NVIDIA_API_KEY=...  uv run python diag_sd_grounding.py

(NVIDIA_API_KEY is only needed for the vector half; without it the script still
runs keyword-only retrieval and tells you so.)
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import text

from plotlot.core.types import NumericZoningParams
from plotlot.pipeline.extraction_verify import (
    _MIN_LOT_PATTERNS,
    _combine_text,
    _ground,
    _ground_for_zone,
    verify_numeric_params,
)
from plotlot.retrieval.search import hybrid_search
from plotlot.storage.db import get_session

MUNI = "San Diego"
ZONE = "RM-3-7"
MAGIC = "1,000 square feet of lot area"  # the text that must ground 6 units

# The queries the pipeline plausibly issues for this parcel.
QUERIES = [
    "RM-3-7",
    "RM-3-7 maximum density dwelling units per lot area",
    "RM zone maximum density dwelling unit per 1,000 square feet of lot area",
]


def _hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


async def main() -> None:
    print(f"DATABASE_URL set: {bool(os.getenv('DATABASE_URL'))}")
    print(f"NVIDIA_API_KEY set: {bool(os.getenv('NVIDIA_API_KEY'))}")

    session = await get_session()
    try:
        # ---- 1. Is San Diego ingested, and is the density chunk present? ----
        _hr("1. INGESTION CHECK (ordinance_chunks)")
        total = (
            await session.execute(
                text("SELECT COUNT(*) FROM ordinance_chunks WHERE municipality ILIKE :m"),
                {"m": f"%{MUNI}%"},
            )
        ).scalar()
        print(f"San Diego chunks total: {total}")

        density_rows = (
            await session.execute(
                text(
                    "SELECT section, section_title, LEFT(chunk_text, 320) AS preview "
                    "FROM ordinance_chunks "
                    "WHERE municipality ILIKE :m AND chunk_text ILIKE :phrase "
                    "ORDER BY section LIMIT 10"
                ),
                {"m": f"%{MUNI}%", "phrase": f"%{MAGIC}%"},
            )
        ).fetchall()
        print(f'\nChunks containing "{MAGIC}": {len(density_rows)}')
        for r in density_rows:
            print(f"  • [{r.section}] {r.section_title}")
            print(f"      {r.preview.strip()[:300]}")

        zoned = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM ordinance_chunks "
                    "WHERE municipality ILIKE :m AND :z = ANY(zone_codes)"
                ),
                {"m": f"%{MUNI}%", "z": ZONE},
            )
        ).scalar()
        print(f"\nChunks tagged with zone_codes containing '{ZONE}': {zoned}")
        if not density_rows:
            print(
                "\n>>> The density chunk is NOT in the DB. This is an INGESTION/chunking "
                "gap, not retrieval. Re-ingest San Diego (the §131.0406 RM table must be "
                "captured as a chunk) before anything else.\n"
            )

        # ---- 2. Does hybrid_search retrieve it, and at what rank? ----
        _hr("2. RETRIEVAL CHECK (real hybrid_search, limit=15, zone_code_boost=RM-3-7)")
        best_results = []
        for q in QUERIES:
            results = await hybrid_search(
                session, MUNI, q, limit=15, zone_code_boost=ZONE
            )
            print(f'\nquery: "{q}"  → {len(results)} results')
            hit_rank = None
            for i, res in enumerate(results, 1):
                has_magic = MAGIC.lower() in (res.chunk_text or "").lower()
                flag = "  <<< DENSITY CHUNK" if has_magic else ""
                if has_magic and hit_rank is None:
                    hit_rank = i
                print(
                    f"  {i:>2}. score={getattr(res, 'score', 0):.4f} "
                    f"[{res.section}] {(res.section_title or '')[:54]}{flag}"
                )
            print(
                f"  → density chunk rank: {hit_rank if hit_rank else 'NOT RETRIEVED in top 15'}"
            )
            if len(results) >= len(best_results):
                best_results = results

        # ---- 3. Does the retrieved text GROUND the value (old vs zone-aware)? ----
        _hr("3. GROUNDING CHECK (real extraction_verify on the retrieved text)")
        combined_text, top_section = _combine_text(best_results)
        print(f"top section: {top_section}")

        old_val, old_snip = _ground(combined_text, _MIN_LOT_PATTERNS)
        print(f"\nOLD (first-match) min-lot-area: {old_val}")
        if old_snip:
            print(f'  evidence: "...{old_snip[:160]}..."')

        new_val, new_snip = _ground_for_zone(combined_text, _MIN_LOT_PATTERNS, ZONE)
        print(f"\nNEW (zone-aware, {ZONE}) min-lot-area: {new_val}")
        if new_snip:
            print(f'  evidence: "...{new_snip[:160]}..."')

        # End-to-end: run the real verifier exactly as the pipeline does.
        params = NumericZoningParams(min_lot_area_per_unit_sqft=1000.0)
        ver = verify_numeric_params(params, best_results, ZONE)
        ml = next((f for f in ver.fields if f.field == "min_lot_area_per_unit_sqft"), None)
        print("\nverify_numeric_params(min_lot=1000, RM-3-7):")
        print(f"  min_lot status   : {ml.status if ml else 'n/a'} (source={ml.source_value if ml else None})")
        print(f"  offer_is_provisional: {ver.offer_is_provisional}")

        _hr("VERDICT")
        if ml and ml.status == "verified" and not ver.offer_is_provisional:
            print(
                "FIXED ✓  Zone-aware grounding reads RM-3-7 → 1,000 sqft/DU, the verifier\n"
                "  marks it VERIFIED, and offer_is_provisional is False → FIRM 6 units.\n"
                f"  (Old first-match grabbed {old_val} — a different RM zone — which is what\n"
                "   produced the spurious 'provisional' before this fix.)"
            )
        elif new_val and abs(new_val - 1000.0) < 50:
            print(
                "PARTIAL  Zone-aware grounding found 1,000 but the verifier still flags\n"
                "  provisional — send me this output and I'll trace verify_numeric_params."
            )
        elif density_rows:
            print(
                "NOT GROUNDED ✗  density chunk exists but zone-aware grounding missed it.\n"
                f"  Check the '{ZONE}' token appears verbatim in the retrieved chunk text."
            )
        else:
            print("NOT IN DB ✗  Re-ingest San Diego so the RM density table is chunked.")
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
