"""PlotLot CLI — ingestion, discovery, search, and property lookup commands."""

import asyncio
import logging
import sys

from plotlot.config import settings
from plotlot.observability.tracing import enable_async_logging, set_experiment, set_tracking_uri


def _init_mlflow() -> None:
    """Initialize MLflow tracking for the current process."""
    set_tracking_uri(settings.mlflow_tracking_uri)
    set_experiment(settings.mlflow_experiment_name)
    enable_async_logging()


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
    has_dims = any([
        report.setbacks.front, report.setbacks.side, report.setbacks.rear,
        report.max_height, report.max_density, report.floor_area_ratio,
        report.lot_coverage, report.min_lot_size,
    ])
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
