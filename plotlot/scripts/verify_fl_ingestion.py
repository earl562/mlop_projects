"""Verify ingestion state for the 10 test municipalities.

Checks:
1. Chunk counts per municipality
2. Dimensional-standard keyword presence (FAR, height, setback, density, lot coverage)
3. Zone code coverage (which zone codes are tagged in chunks)
"""

import asyncio
import os
import sys
import asyncpg

# Load .env
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

# Convert SQLAlchemy URL to asyncpg format if needed
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

# 10 test municipalities (deduplicated)
TEST_MUNICIPALITIES = [
    "Miami",
    "Coral Springs",
    "Davie",
    "Pompano Beach",
    "Fort Lauderdale",
    "Oakland Park",
    "Lake Worth Beach",
]

# Dimensional standard keywords to search for
DIMENSIONAL_KEYWORDS = {
    "FAR": r"(?:floor\s*area\s*ratio|\bFAR\b)",
    "height": r"(?:max(?:imum)?\s*height|height\s*(?:limit|restriction|regulation))",
    "setback": r"(?:setback|set\s*back|front\s*yard|rear\s*yard|side\s*yard)",
    "density": r"(?:density|dwelling\s*units?\s*per\s*acre|units?\s*per\s*acre|du/ac)",
    "lot_coverage": r"(?:lot\s*coverage|impervious\s*(?:area|surface))",
    "min_lot_size": r"(?:minimum\s*lot\s*(?:size|area)|min(?:imum)?\s*lot)",
}


async def main():
    conn = await asyncpg.connect(DATABASE_URL)

    print("=" * 80)
    print("INGESTION STATE FOR 10 TEST MUNICIPALITIES")
    print("=" * 80)

    # 1. Overall chunk counts
    print("\n## 1. Chunk Counts Per Municipality\n")
    print(f"{'Municipality':<25} {'State':<6} {'Chunks':>8} {'Has Embeddings':>15}")
    print("-" * 60)

    for muni in TEST_MUNICIPALITIES:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as chunk_count,
                COUNT(embedding) as embedded_count
            FROM ordinance_chunks
            WHERE municipality ILIKE $1
            """,
            f"%{muni}%",
        )
        chunks = row["chunk_count"] or 0
        embedded = row["embedded_count"] or 0
        print(f"{muni:<25} {'FL':<6} {chunks:>8} {f'{embedded}/{chunks}':>15}")

    # 2. Dimensional standard keyword presence
    print("\n## 2. Dimensional Standard Keyword Presence\n")
    header = f"{'Municipality':<25}"
    for kw in DIMENSIONAL_KEYWORDS:
        header += f" {kw:>14}"
    print(header)
    print("-" * (25 + 15 * len(DIMENSIONAL_KEYWORDS)))

    results = {}
    for muni in TEST_MUNICIPALITIES:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE chunk_text ILIKE '%floor area ratio%' OR chunk_text ILIKE '%FAR%') as far,
                COUNT(*) FILTER (WHERE chunk_text ILIKE '%height%') as height,
                COUNT(*) FILTER (WHERE chunk_text ILIKE '%setback%') as setback,
                COUNT(*) FILTER (WHERE chunk_text ILIKE '%density%' OR chunk_text ILIKE '%dwelling units per acre%') as density,
                COUNT(*) FILTER (WHERE chunk_text ILIKE '%lot coverage%') as lot_coverage,
                COUNT(*) FILTER (WHERE chunk_text ILIKE '%minimum lot%') as min_lot_size,
                COUNT(*) as total
            FROM ordinance_chunks
            WHERE municipality ILIKE $1
            """,
            f"%{muni}%",
        )
        results[muni] = row
        line = f"{muni:<25}"
        line += f" {row['far']:>14}"
        line += f" {row['height']:>14}"
        line += f" {row['setback']:>14}"
        line += f" {row['density']:>14}"
        line += f" {row['lot_coverage']:>14}"
        line += f" {row['min_lot_size']:>14}"
        print(line)

    # 3. Zone codes present in chunks
    print("\n## 3. Zone Codes Tagged in Chunks\n")
    for muni in TEST_MUNICIPALITIES:
        rows = await conn.fetch(
            """
            SELECT DISTINCT zone_code
            FROM ordinance_chunks, unnest(zone_codes) AS zone_code
            WHERE municipality ILIKE $1
            ORDER BY zone_code
            """,
            f"%{muni}%",
        )
        codes = [r["zone_code"] for r in rows] if rows else []
        print(f"  {muni}: {', '.join(codes) if codes else '(none)'}")

    # 4. Sample chunk text for first municipality with chunks (sanity check)
    print("\n## 4. Sample Chunk Text (first municipality with chunks)\n")
    for muni in TEST_MUNICIPALITIES:
        row = await conn.fetchrow(
            """
            SELECT chunk_text, section_title, chapter, zone_codes
            FROM ordinance_chunks
            WHERE municipality ILIKE $1
            ORDER BY chunk_index
            LIMIT 1
            """,
            f"%{muni}%",
        )
        if row:
            print(f"  Municipality: {muni}")
            print(f"  Chapter: {row['chapter'] or 'N/A'}")
            print(f"  Section: {row['section_title'] or 'N/A'}")
            print(f"  Zone codes: {row['zone_codes'] or '[]'}")
            text = row["chunk_text"][:500]
            print(f"  Text (first 500 chars): {text}")
            print()
            break
    else:
        print("  No chunks found for any test municipality!")

    # 5. Total ingestion overview
    print("\n## 5. Total Ingestion Overview\n")
    rows = await conn.fetch(
        """
        SELECT municipality, state, COUNT(*) as chunks
        FROM ordinance_chunks
        GROUP BY municipality, state
        ORDER BY chunks DESC
        LIMIT 30
        """
    )
    print(f"{'Municipality':<30} {'State':<6} {'Chunks':>8}")
    print("-" * 50)
    for r in rows:
        print(f"{r['municipality']:<30} {r['state'] or 'N/A':<6} {r['chunks']:>8}")

    total = await conn.fetchval("SELECT COUNT(*) FROM ordinance_chunks")
    total_munis = await conn.fetchval(
        "SELECT COUNT(DISTINCT municipality) FROM ordinance_chunks"
    )
    print(f"\n  TOTAL: {total} chunks across {total_munis} municipalities")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
