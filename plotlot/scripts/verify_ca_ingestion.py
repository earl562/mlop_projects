"""End-to-end verification of CA municipality ingestion.

Tests the full retrieval + LLM extraction pipeline for each ingested CA city.
Checks:
  1. Chunk count in DB (flags cities with < MIN_CHUNKS as suspect)
  2. Hybrid search returns relevant ordinance sections
  3. LLM extracts at least one numeric zoning parameter

Run with:
    uv run python scripts/verify_ca_ingestion.py

Flags:
    --county <name>   Only test one county (e.g. --county alameda)
    --quick           Skip LLM extraction (retrieval check only)
    --list            Just print what's in the DB, no tests
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Test cases — keyed by the exact municipality name stored in the DB.
# Address is used only for LLM context (not geocoded).
# ---------------------------------------------------------------------------

TEST_CASES: list[dict] = [
    # Sacramento county (discovered: Citrus Heights, Lincoln, Rocklin)
    {"municipality": "Citrus Heights", "county": "Sacramento", "address": "6360 Fountain Square Dr, Citrus Heights, CA 95621", "zone_query": "residential zone height setback density"},
    {"municipality": "Lincoln", "county": "Sacramento", "address": "600 6th St, Lincoln, CA 95648", "zone_query": "residential zone setback density lot coverage"},
    {"municipality": "Rocklin", "county": "Sacramento", "address": "3970 Rocklin Rd, Rocklin, CA 95677", "zone_query": "residential density setback height FAR"},
    # Contra Costa county (discovered: El Cerrito, Lafayette, Moraga, Orinda, Richmond)
    {"municipality": "El Cerrito", "county": "Contra Costa", "address": "10890 San Pablo Ave, El Cerrito, CA 94530", "zone_query": "residential zone height setback density"},
    {"municipality": "Lafayette", "county": "Contra Costa", "address": "3675 Mt Diablo Blvd, Lafayette, CA 94549", "zone_query": "residential zone setback density lot coverage"},
    {"municipality": "Moraga", "county": "Contra Costa", "address": "329 Rheem Blvd, Moraga, CA 94556", "zone_query": "residential density height setback"},
    {"municipality": "Orinda", "county": "Contra Costa", "address": "22 Orinda Way, Orinda, CA 94563", "zone_query": "residential zone setback lot size density"},
    {"municipality": "Richmond", "county": "Contra Costa", "address": "450 Civic Center Plaza, Richmond, CA 94804", "zone_query": "residential zone density height setback"},
    # Alameda county (discovered: Alameda city, Hayward, Newark, Oakland)
    {"municipality": "Alameda", "county": "Alameda", "address": "2263 Santa Clara Ave, Alameda, CA 94501", "zone_query": "residential zone height setback density"},
    {"municipality": "Hayward", "county": "Alameda", "address": "777 B St, Hayward, CA 94541", "zone_query": "residential zone height setback density"},
    {"municipality": "Newark", "county": "Alameda", "address": "37101 Newark Blvd, Newark, CA 94560", "zone_query": "residential density setback height lot coverage"},
    {"municipality": "Oakland", "county": "Alameda", "address": "250 Frank H Ogawa Plaza, Oakland, CA 94612", "zone_query": "residential zone density setback height RM"},
    # Santa Clara county (9 cities)
    {"municipality": "San Jose", "county": "Santa Clara", "address": "200 E Santa Clara St, San Jose, CA 95113", "zone_query": "residential zone density setback height"},
    {"municipality": "Milpitas", "county": "Santa Clara", "address": "455 E Calaveras Blvd, Milpitas, CA 95035", "zone_query": "residential density setback height lot coverage"},
    {"municipality": "Mountain View", "county": "Santa Clara", "address": "500 Castro St, Mountain View, CA 94041", "zone_query": "residential zone height setback density"},
    {"municipality": "Campbell", "county": "Santa Clara", "address": "70 N First St, Campbell, CA 95008", "zone_query": "residential density setback height FAR"},
    {"municipality": "Los Altos", "county": "Santa Clara", "address": "1 N San Antonio Rd, Los Altos, CA 94022", "zone_query": "residential setback height lot coverage density"},
    {"municipality": "Morgan Hill", "county": "Santa Clara", "address": "17575 Peak Ave, Morgan Hill, CA 95037", "zone_query": "residential zone density setback"},
    {"municipality": "Monte Sereno", "county": "Santa Clara", "address": "18041 Saratoga Los Gatos Rd, Monte Sereno, CA 95030", "zone_query": "residential setback lot size height density"},
    {"municipality": "Saratoga", "county": "Santa Clara", "address": "13777 Fruitvale Ave, Saratoga, CA 95070", "zone_query": "residential height setback lot coverage"},
    {"municipality": "Los Gatos", "county": "Santa Clara", "address": "110 E Main Ave, Los Gatos, CA 95030", "zone_query": "residential zone setback density height"},
    # San Mateo county (discovered: East Palo Alto, Daly City, Hillsborough, Portola Valley, Woodside + suspects)
    {"municipality": "East Palo Alto", "county": "San Mateo", "address": "2415 University Ave, East Palo Alto, CA 94303", "zone_query": "residential zone density height setback"},
    {"municipality": "Daly City", "county": "San Mateo", "address": "333 90th St, Daly City, CA 94015", "zone_query": "residential zone setback density height"},
    {"municipality": "Hillsborough", "county": "San Mateo", "address": "1600 Floribunda Ave, Hillsborough, CA 94010", "zone_query": "residential setback lot size height density"},
    {"municipality": "Portola Valley", "county": "San Mateo", "address": "765 Portola Rd, Portola Valley, CA 94028", "zone_query": "residential setback lot size density height"},
    {"municipality": "Woodside", "county": "San Mateo", "address": "2955 Woodside Rd, Woodside, CA 94062", "zone_query": "residential zone setback lot size density"},
    # Suspects — low chunk counts, likely wrong Municode product
    {"municipality": "Redwood City", "county": "San Mateo", "address": "1017 Middlefield Rd, Redwood City, CA 94063", "zone_query": "residential zone density setback height"},
    {"municipality": "Belmont", "county": "San Mateo", "address": "1 Twin Pines Ln, Belmont, CA 94002", "zone_query": "residential zone height setback density"},
]

MIN_CHUNKS = 100  # below this → flag as suspect

# ---------------------------------------------------------------------------


@dataclass
class VerifyResult:
    municipality: str
    county: str
    db_chunks: int
    search_hits: int
    params_extracted: int
    params: dict = field(default_factory=dict)
    error: str = ""
    elapsed_s: float = 0.0

    def passed(self, quick: bool = False) -> bool:
        if self.error:
            return False
        if quick:
            return self.search_hits >= 3
        return self.search_hits >= 3 and self.params_extracted >= 1

    @property
    def suspect(self) -> bool:
        return self.db_chunks < MIN_CHUNKS


async def _count_chunks(session, municipality: str) -> int:
    from sqlalchemy import text

    row = await session.execute(
        text("SELECT COUNT(*) FROM ordinance_chunks WHERE municipality = :m"),
        {"m": municipality},
    )
    return row.scalar() or 0


async def verify_one(
    tc: dict,
    quick: bool = False,
) -> VerifyResult:
    from plotlot.retrieval.llm import analyze_zoning
    from plotlot.retrieval.search import hybrid_search
    from plotlot.storage.db import get_session

    t0 = time.monotonic()
    result = VerifyResult(
        municipality=tc["municipality"],
        county=tc["county"],
        db_chunks=0,
        search_hits=0,
        params_extracted=0,
    )

    session = None
    try:
        session = await get_session()
        result.db_chunks = await _count_chunks(session, tc["municipality"])
        search_results = await hybrid_search(
            session=session,
            municipality=tc["municipality"],
            zone_code=tc["zone_query"],
            limit=10,
        )
        result.search_hits = len(search_results)

        if not quick and search_results:
            raw = await analyze_zoning(
                address=tc["address"],
                municipality=tc["municipality"],
                county=tc["county"],
                results=search_results,
            )
            numeric = raw.get("numeric_params", raw)
            extracted = {k: v for k, v in numeric.items() if v is not None and v != 0}
            result.params = extracted
            result.params_extracted = len(extracted)

    except Exception as e:
        result.error = str(e)
    finally:
        if session:
            await session.close()

    result.elapsed_s = time.monotonic() - t0
    return result


def _print_result(r: VerifyResult, quick: bool) -> None:
    status = "PASS" if r.passed(quick) else ("SUSPECT" if r.suspect else "FAIL")
    icon = {"PASS": "✓", "SUSPECT": "⚠", "FAIL": "✗"}[status]
    chunks_warn = " ⚠ LOW" if r.suspect else ""
    print(f"  {icon} {r.municipality:<20} db={r.db_chunks:>5}{chunks_warn}  hits={r.search_hits}", end="")
    if not quick:
        print(f"  params={r.params_extracted}", end="")
    print(f"  ({r.elapsed_s:.1f}s)")
    if r.error:
        print(f"      ERROR: {r.error}")
    if not quick and r.params:
        top = list(r.params.items())[:4]
        print(f"      extracted: {dict(top)}")


async def main(county_filter: str | None, quick: bool) -> None:
    cases = TEST_CASES
    if county_filter:
        cases = [tc for tc in TEST_CASES if tc["county"].lower().replace(" ", "_") == county_filter.lower().replace(" ", "_")]
        if not cases:
            print(f"No test cases for county '{county_filter}'. Available: {sorted({tc['county'] for tc in TEST_CASES})}")
            sys.exit(1)

    mode = "quick (retrieval only)" if quick else "full (retrieval + LLM extraction)"
    print(f"\nPlotLot CA Ingestion Verification — {mode}")
    print(f"{'=' * 62}")

    by_county: dict[str, list[dict]] = {}
    for tc in cases:
        by_county.setdefault(tc["county"], []).append(tc)

    all_results: list[VerifyResult] = []

    for county, county_cases in by_county.items():
        print(f"\n  {county}")
        print(f"  {'─' * 40}")
        if quick:
            # Parallel is fine in quick mode — no LLM calls, connections release fast
            results = await asyncio.gather(*[verify_one(tc, quick=True) for tc in county_cases])
        else:
            # Sequential in full mode — LLM calls hold connections too long for parallel
            results = []
            for tc in county_cases:
                results.append(await verify_one(tc, quick=False))
        for r in results:
            _print_result(r, quick)
            all_results.append(r)

    passed = sum(1 for r in all_results if r.passed(quick))
    suspects = sum(1 for r in all_results if r.suspect)
    failed = sum(1 for r in all_results if r.error)

    print(f"\n{'=' * 62}")
    print(f"  Results: {passed}/{len(all_results)} passed  |  {suspects} suspect (low chunks)  |  {failed} errors")
    if suspects:
        print("\n  Suspect municipalities (likely wrong Municode product):")
        for r in all_results:
            if r.suspect:
                print(f"    - {r.municipality} ({r.county}): {r.db_chunks} chunks")
    print()


async def list_db() -> None:
    from plotlot.storage.db import get_session
    from sqlalchemy import text

    session = await get_session()
    rows = await session.execute(text(
        "SELECT municipality, state, COUNT(*) as chunks "
        "FROM ordinance_chunks GROUP BY municipality, state ORDER BY state, municipality"
    ))
    results = rows.fetchall()
    await session.close()

    print(f"\n{'Municipality':<35} {'State':<6} Chunks")
    print("─" * 55)
    total = 0
    for row in results:
        flag = " ⚠ LOW" if row.chunks < MIN_CHUNKS else ""
        print(f"{row.municipality:<35} {row.state:<6} {row.chunks:>6}{flag}")
        total += row.chunks
    print("─" * 55)
    print(f"{'TOTAL':<35} {'':6} {total:>6}")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]
    county_filter = None
    quick = "--quick" in args

    if "--list" in args:
        asyncio.run(list_db())
        sys.exit(0)

    if "--county" in args:
        idx = args.index("--county")
        if idx + 1 < len(args):
            county_filter = args[idx + 1]

    asyncio.run(main(county_filter, quick))
