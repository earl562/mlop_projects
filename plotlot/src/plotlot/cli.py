"""PlotLot CLI — ingestion, discovery, search, and property lookup commands."""

import asyncio
import logging
import sys

from plotlot.config import settings
from plotlot.observability.tracing import configure_mlflow


def _init_mlflow() -> None:
    """Initialize MLflow tracking for the current process."""
    if not configure_mlflow(settings.mlflow_tracking_uri, settings.mlflow_experiment_name):
        logging.getLogger(__name__).warning(
            "MLflow tracing unavailable — continuing without tracing"
        )


def main() -> None:
    """Run a property lookup: plotlot <address>"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _init_mlflow()

    if len(sys.argv) < 2:
        print("Usage: plotlot <address>")
        print('  Example: plotlot "7940 Plantation Blvd, Miramar, FL"')
        print('  Example: plotlot "171 NE 209th Ter, Miami, FL 33179"')
        sys.exit(1)

    address = " ".join(sys.argv[1:])
    asyncio.run(_property_lookup(address))


async def _property_lookup(address: str) -> None:
    """Full address → geocode → search → LLM analysis pipeline."""
    from plotlot.pipeline.lookup import lookup_address

    print("\nPlotLot Zoning Analysis")
    print(f"{'=' * 50}")
    print(f"Looking up: {address}\n")

    report = await lookup_address(address)

    if not report:
        print("Could not analyze this address. Check the address and try again.")
        return

    # Header
    print(f"Address:      {report.formatted_address}")
    print(f"Municipality: {report.municipality}")
    print(f"County:       {report.county}")
    if report.lat and report.lng:
        print(f"Coordinates:  {report.lat}, {report.lng}")
    print()

    # Property record (from county PA)
    prop = report.property_record
    if prop:
        print(f"{'─' * 50}")
        print("Property Record (County Property Appraiser):")
        if prop.folio:
            print(f"  Folio:          {prop.folio}")
        if prop.owner:
            print(f"  Owner:          {prop.owner}")
        if prop.zoning_code:
            print(f"  Zoning Code:    {prop.zoning_code}")
        if prop.zoning_description:
            print(f"  Zoning Desc:    {prop.zoning_description}")
        if prop.land_use_description:
            print(f"  Land Use:       {prop.land_use_description}")
        if prop.lot_size_sqft:
            print(f"  Lot Size:       {prop.lot_size_sqft:,.0f} sq ft")
        if prop.lot_dimensions:
            print(f"  Lot Dimensions: {prop.lot_dimensions}")
        if prop.bedrooms or prop.bathrooms:
            bath_str = f"{prop.bathrooms:g}"
            if prop.half_baths:
                bath_str += f" / {prop.half_baths} half"
            print(f"  Beds / Baths:   {prop.bedrooms} / {bath_str}")
        if prop.floors:
            print(f"  Floors:         {prop.floors}")
        if prop.living_area_sqft:
            print(f"  Living Area:    {prop.living_area_sqft:,.0f} sq ft")
        if prop.building_area_sqft:
            print(f"  Building Area:  {prop.building_area_sqft:,.0f} sq ft")
        if prop.year_built:
            print(f"  Year Built:     {prop.year_built}")
        if prop.assessed_value:
            print(f"  Assessed Value: ${prop.assessed_value:,.0f}")
        if prop.last_sale_price:
            sale_info = f"${prop.last_sale_price:,.0f}"
            if prop.last_sale_date:
                sale_info += f" ({prop.last_sale_date})"
            print(f"  Last Sale:      {sale_info}")
        print()

    # Zoning classification
    if report.zoning_district:
        print(f"Zoning District: {report.zoning_district}")
    if report.zoning_description:
        print(f"Description:     {report.zoning_description}")
    print()

    # Summary
    if report.summary:
        print("Summary:")
        print(f"  {report.summary}")
        print()

    # Dimensional standards
    has_dims = any(
        [
            report.setbacks.front,
            report.setbacks.side,
            report.setbacks.rear,
            report.max_height,
            report.max_density,
            report.floor_area_ratio,
            report.lot_coverage,
            report.min_lot_size,
        ]
    )
    if has_dims:
        print("Dimensional Standards:")
        if report.setbacks.front:
            print(f"  Front setback:  {report.setbacks.front}")
        if report.setbacks.side:
            print(f"  Side setback:   {report.setbacks.side}")
        if report.setbacks.rear:
            print(f"  Rear setback:   {report.setbacks.rear}")
        if report.max_height:
            print(f"  Max height:     {report.max_height}")
        if report.max_density:
            print(f"  Max density:    {report.max_density}")
        if report.floor_area_ratio:
            print(f"  FAR:            {report.floor_area_ratio}")
        if report.lot_coverage:
            print(f"  Lot coverage:   {report.lot_coverage}")
        if report.min_lot_size:
            print(f"  Min lot size:   {report.min_lot_size}")
        print()

    # Max allowable units
    da = report.density_analysis
    if da:
        print(f"{'─' * 50}")
        print(f"MAX ALLOWABLE UNITS: {da.max_units}")
        print(f"Governing constraint: {da.governing_constraint}")
        print()
        if da.constraints:
            print("Constraint breakdown:")
            for c in da.constraints:
                marker = "  >>> GOVERNING" if c.is_governing else ""
                unit_label = "unit" if c.max_units == 1 else "units"
                print(f"  [{c.name}] {c.max_units} {unit_label} — {c.formula}{marker}")
            print()
        if da.notes:
            print("Notes:")
            for note in da.notes:
                print(f"  - {note}")
            print()
        print(f"Calculation confidence: {da.confidence}")
        print(f"{'─' * 50}")
        print()

    # Uses
    if report.allowed_uses:
        print("Allowed Uses:")
        for use in report.allowed_uses:
            print(f"  - {use}")
        print()

    if report.conditional_uses:
        print("Conditional Uses:")
        for use in report.conditional_uses:
            print(f"  - {use}")
        print()

    if report.prohibited_uses:
        print("Prohibited Uses:")
        for use in report.prohibited_uses:
            print(f"  - {use}")
        print()

    # Parking
    if report.parking_requirements:
        print(f"Parking: {report.parking_requirements}")
        print()

    # Sources
    if report.sources:
        print(f"Sources ({len(report.sources)} ordinance sections):")
        for src in report.sources[:5]:
            print(f"  - {src}")
        if len(report.sources) > 5:
            print(f"  ... and {len(report.sources) - 5} more")
        print()

    if report.confidence:
        print(f"Confidence: {report.confidence}")


def ingest_main() -> None:
    """Run the ingestion pipeline: plotlot-ingest [--all | --discover | <municipality_key>]"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from plotlot.core.types import MUNICODE_CONFIGS

    args = sys.argv[1:]
    if not args or args[0] == "--help":
        print("Usage: plotlot-ingest [--all | --discover | --state XX | --resume ID | <key>]")
        print(f"  Fallback keys: {', '.join(MUNICODE_CONFIGS)}")
        print("  --all              Ingest all discovered municipalities (FL, NC, TX, GA, SC, CA)")
        print("  --state FL         Ingest only one state (FL, NC, TX, GA, SC, CA)")
        print("  --resume BATCH_ID  Resume a previously interrupted batch")
        print("  --discover         Run discovery across all 5 states and print results")
        print("  <key>              Ingest a single municipality by key")
        sys.exit(0 if "--help" in args else 1)

    if args[0] == "--discover":
        _run_discover()
    elif args[0] in ("--all", "--state", "--resume"):
        from plotlot.core.errors import NvidiaCreditsExhaustedError
        from plotlot.pipeline.ingest import ingest_all

        state_filter = None
        resume_batch = None

        # Parse flags
        i = 0
        while i < len(args):
            if args[i] == "--state" and i + 1 < len(args):
                state_filter = args[i + 1]
                i += 2
            elif args[i] == "--resume" and i + 1 < len(args):
                resume_batch = args[i + 1]
                i += 2
            else:
                i += 1

        try:
            results = asyncio.run(ingest_all(state_filter=state_filter, resume_batch=resume_batch))
        except NvidiaCreditsExhaustedError as e:
            _print_credits_exhausted(str(e))
            sys.exit(2)

        print("\nIngestion results:")
        for key, count in sorted(results.items()):
            status = f"{count} chunks" if count > 0 else "FAILED"
            print(f"  {key:<35} {status}")

        total = sum(results.values())
        succeeded = sum(1 for v in results.values() if v > 0)
        failed = sum(1 for v in results.values() if v == 0)
        print(f"\nTotal: {total} chunks | {succeeded} succeeded | {failed} failed")
    else:
        from plotlot.core.errors import NvidiaCreditsExhaustedError
        from plotlot.pipeline.ingest import ingest_municipality

        key = args[0]
        try:
            count = asyncio.run(ingest_municipality(key))
        except NvidiaCreditsExhaustedError as e:
            _print_credits_exhausted(str(e))
            sys.exit(2)
        print(f"\nIngested {count} chunks for {key}")


def _print_credits_exhausted(detail: str) -> None:
    print("\n" + "=" * 60)
    print("  ⛔  NVIDIA NIM CREDITS EXHAUSTED — INGESTION STOPPED")
    print("=" * 60)
    print(f"\n  {detail}\n")
    print("  Progress so far has been saved via checkpoints.")
    print("  Your options:\n")
    print("  1. Upgrade NVIDIA NIM ($0.06 / 1M tokens — ~$0.50 for all NorCal):")
    print("     https://build.nvidia.com\n")
    print("  2. Swap key in .env once upgraded, then resume:")
    print("     plotlot-ingest --resume <batch_id>  (or re-run --all)")
    print("\n  Already-indexed municipalities are serving live traffic.")
    print("=" * 60 + "\n")


def _run_discover() -> None:
    """Run municipality discovery across all supported states."""
    from plotlot.ingestion.discovery import get_all_municode_configs

    print("Discovering municipalities on Municode (FL, NC, TX, GA, SC)...")
    print("(This queries the Municode Library API — takes ~60-120s)\n")

    configs = asyncio.run(get_all_municode_configs(force_refresh=True))

    if not configs:
        print("Discovery returned 0 results. The Library API may be down.")
        return

    by_state: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for key, config in sorted(configs.items()):
        state = config.state
        county = config.county
        by_state.setdefault(state, {}).setdefault(county, []).append((key, config.municipality))

    for state in sorted(by_state):
        state_total = sum(len(munis) for munis in by_state[state].values())
        print(f"\n{'=' * 60}")
        print(f"  {state} — {state_total} municipalities")
        print(f"{'=' * 60}")
        for county in sorted(by_state[state]):
            munis = by_state[state][county]
            print(f"\n  {county.upper()} ({len(munis)}):")
            for key, name in munis:
                print(f"    {key:<35} {name}")

    print(f"\nTotal: {len(configs)} municipalities across {len(by_state)} states")
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
