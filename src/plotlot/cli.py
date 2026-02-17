"""PlotLot CLI — ingestion, discovery, and search commands."""

import asyncio
import logging
import sys


def main() -> None:
    """Run a property lookup: plotlot <address>"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: plotlot <address>")
        print('  Example: plotlot "123 NW 5th Ave, Fort Lauderdale, FL"')
        sys.exit(1)

    address = " ".join(sys.argv[1:])
    print(f"Property lookup for: {address}")
    print("(Not yet implemented — Phase 3)")


def ingest_main() -> None:
    """Run the ingestion pipeline: plotlot-ingest [--all | --discover | <municipality_key>]"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from plotlot.core.types import MUNICODE_CONFIGS

    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print("Usage: plotlot-ingest [--all | --discover | <municipality_key>]")
        print(f"  Fallback keys: {', '.join(MUNICODE_CONFIGS)}")
        print("  --all:      Ingest all discovered municipalities (~73)")
        print("  --discover: Run discovery and print all found municipalities")
        print("  <key>:      Ingest a single municipality by key")
        sys.exit(0 if sys.argv[1:] == ["--help"] else 1)

    if sys.argv[1] == "--discover":
        _run_discover()
    elif sys.argv[1] == "--all":
        from plotlot.pipeline.ingest import ingest_all
        results = asyncio.run(ingest_all())
        print("\nIngestion results:")
        for key, count in sorted(results.items()):
            print(f"  {key}: {count} chunks")
        total = sum(results.values())
        print(f"\nTotal: {total} chunks across {len(results)} municipalities")
    else:
        key = sys.argv[1]
        from plotlot.pipeline.ingest import ingest_municipality
        count = asyncio.run(ingest_municipality(key))
        print(f"\nIngested {count} chunks for {key}")


def _run_discover() -> None:
    """Run municipality discovery and print results."""
    from plotlot.ingestion.discovery import discover_all

    print("Discovering municipalities on Municode...")
    print("(This queries the Municode Library API — takes ~30-60s)\n")

    configs = asyncio.run(discover_all())

    if not configs:
        print("Discovery returned 0 results. The Library API may be down.")
        return

    by_county: dict[str, list[tuple[str, str]]] = {}
    for key, config in sorted(configs.items()):
        county = config.county
        by_county.setdefault(county, []).append((key, config.municipality))

    for county in sorted(by_county):
        munis = by_county[county]
        print(f"\n{county.upper()} ({len(munis)} municipalities):")
        for key, name in munis:
            print(f"  {key:<35} {name}")

    print(f"\nTotal: {len(configs)} municipalities with zoning data on Municode")
    print("\nTo ingest all: plotlot-ingest --all")


def search_main() -> None:
    """Test hybrid search: plotlot-search <municipality> <zone_code>"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if len(sys.argv) < 3:
        print("Usage: plotlot-search <municipality> <zone_code>")
        print('  Example: plotlot-search "Miami" "T6-80"')
        sys.exit(1)

    municipality = sys.argv[1]
    zone_code = sys.argv[2]

    async def _run():
        from plotlot.retrieval.search import hybrid_search
        from plotlot.storage.db import get_session

        session = await get_session()
        try:
            results = await hybrid_search(session, municipality, zone_code)
            print(f"\nFound {len(results)} results for {municipality} / {zone_code}:\n")
            for i, r in enumerate(results, 1):
                print(f"--- Result {i} (score={r.score:.4f}) ---")
                print(f"Section: {r.section} — {r.section_title}")
                print(f"Zone codes: {r.zone_codes}")
                print(f"Text: {r.chunk_text[:300]}...")
                print()
        finally:
            await session.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
