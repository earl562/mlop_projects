"""PlotLot CLI — ingestion, discovery, search, and property lookup commands."""

import asyncio
import json
import logging
import sys
from pathlib import Path

from plotlot.config import settings
from plotlot.observability.tracing import configure_mlflow

# ~/.plotlot/nvidia_credits_used.json — persists cumulative credit usage across runs
_CREDITS_FILE = Path.home() / ".plotlot" / "nvidia_credits_used.json"
# NVIDIA free tier allocation
_NVIDIA_FREE_CREDITS = 1000


def _load_cumulative_credits() -> int:
    """Load total credits used across all prior runs."""
    try:
        if _CREDITS_FILE.exists():
            return int(json.loads(_CREDITS_FILE.read_text()).get("total_api_calls", 0))
    except Exception:
        pass
    return 0


def _save_cumulative_credits(total: int) -> None:
    """Persist cumulative credit usage to disk."""
    try:
        _CREDITS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CREDITS_FILE.write_text(json.dumps({"total_api_calls": total}))
    except Exception as exc:
        logging.getLogger(__name__).warning("Could not save credit usage: %s", exc)


def _print_credit_summary(
    county: str,
    results: dict[str, int],
    calls_this_run: int,
    prior_calls: int,
) -> None:
    """Print credit usage summary after a county run."""
    from plotlot.ingestion.embedder import BATCH_SIZE

    total_calls = prior_calls + calls_this_run
    remaining = max(0, _NVIDIA_FREE_CREDITS - total_calls)
    chunks_this_run = sum(results.values())

    # Each batch ≈ BATCH_SIZE chunks → estimate chunks per call
    chunks_per_call = BATCH_SIZE  # conservative estimate

    # Estimate how many more municipalities could be ingested
    # Use this run's average as the baseline
    munis_this_run = sum(1 for v in results.values() if v > 0)
    avg_chunks_per_muni = (chunks_this_run / munis_this_run) if munis_this_run else 500
    calls_per_muni = max(1, avg_chunks_per_muni / chunks_per_call)
    munis_remaining_est = int(remaining / calls_per_muni) if calls_per_muni > 0 else 0

    print("\n" + "=" * 62)
    print(f"  COUNTY COMPLETE: {county.upper().replace('_', ' ')}")
    print("=" * 62)
    print(f"  Chunks ingested this run : {chunks_this_run:,}")
    print(f"  Municipalities succeeded : {munis_this_run} / {len(results)}")
    print()
    print("  ── NVIDIA Credit Usage ──────────────────────────────────")
    print(f"  API calls this run       : {calls_this_run:,}")
    print(f"  Cumulative calls (total) : {total_calls:,} / {_NVIDIA_FREE_CREDITS:,}")
    print(f"  Credits remaining (est.) : {remaining:,}")
    print()
    if remaining > 0:
        print(
            f"  At ~{avg_chunks_per_muni:.0f} chunks/municipality ({calls_per_muni:.1f} calls each):"
        )
        print(f"  Estimated municipalities left: ~{munis_remaining_est}")
        print()
        print("  Next county commands:")
        print("    plotlot-ingest --state CA --county contra_costa")
        print("    plotlot-ingest --state CA --county alameda")
        print("    plotlot-ingest --state CA --county santa_clara")
        print("    plotlot-ingest --state CA --county san_mateo")
        print("    plotlot-ingest --state CA --county san_francisco")
    else:
        print("  ⚠  Free credits exhausted. Upgrade to continue:")
        print("     https://build.nvidia.com")
    print("=" * 62 + "\n")


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
        print(
            "Usage: plotlot-ingest [--all | --discover | --state XX [--county YY | --counties Y1 Y2 ...] | --resume ID | <key>]"
        )
        print(f"  Fallback keys: {', '.join(MUNICODE_CONFIGS)}")
        print(
            "  --all                                  Ingest all discovered municipalities (FL, NC, TX, GA, SC, CA)"
        )
        print("  --state FL                             Ingest only one state")
        print(
            "  --state CA --county sacramento         Ingest one county (manual county-by-county mode)"
        )
        print(
            "  --state CA --counties c1 c2 c3         Ingest multiple counties in order, stop on credit exhaustion"
        )
        print("  --resume BATCH_ID                      Resume a previously interrupted batch")
        print(
            "  --discover                             Run discovery across all states and print results"
        )
        print("  <key>                                  Ingest a single municipality by key")
        print()
        print(
            "  County keys for CA: sacramento, contra_costa, alameda, santa_clara, san_mateo, san_francisco"
        )
        print(
            "  --san-diego                            Ingest San Diego from city-hosted PDFs (not on Municode)"
        )
        sys.exit(0 if "--help" in args else 1)

    if "--san-diego" in args:
        from plotlot.pipeline.ingest import ingest_san_diego

        count = asyncio.run(ingest_san_diego())
        print(f"San Diego ingestion complete: {count:,} chunks stored")
        sys.exit(0)

    # Parse all flags upfront
    state_filter: str | None = None
    county_filter: str | None = None
    counties_filter: list[str] = []
    resume_batch: str | None = None
    mode = args[0]

    i = 0
    while i < len(args):
        if args[i] == "--state" and i + 1 < len(args):
            state_filter = args[i + 1]
            i += 2
        elif args[i] == "--county" and i + 1 < len(args):
            county_filter = args[i + 1]
            i += 2
        elif args[i] == "--counties":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                counties_filter.append(args[i])
                i += 1
        elif args[i] == "--resume" and i + 1 < len(args):
            resume_batch = args[i + 1]
            i += 2
        else:
            i += 1

    if mode == "--discover":
        _run_discover()

    elif mode in ("--all", "--state", "--resume") and counties_filter:
        # Multi-county sequential ingestion — stops cleanly on credit exhaustion
        from plotlot.core.errors import NvidiaCreditsExhaustedError
        from plotlot.ingestion.embedder import get_api_calls, reset_api_calls
        from plotlot.pipeline.ingest import ingest_county

        if not state_filter:
            print(
                "Error: --counties requires --state. Example: --state CA --counties san_mateo san_francisco"
            )
            sys.exit(1)

        prior_calls = _load_cumulative_credits()
        total_chunks = 0

        for county in counties_filter:
            reset_api_calls()
            print(f"\n{'=' * 62}")
            print(f"  Starting county: {county.upper()}")
            print(f"  Credits used so far: {prior_calls} / {_NVIDIA_FREE_CREDITS}")
            print(f"{'=' * 62}")

            try:
                results = asyncio.run(ingest_county(state_filter, county))
            except NvidiaCreditsExhaustedError as e:
                calls_this_run = get_api_calls()
                _save_cumulative_credits(prior_calls + calls_this_run)
                prior_calls += calls_this_run
                _print_credits_exhausted(str(e))
                print(
                    f"\n  Completed {counties_filter.index(county)} of {len(counties_filter)} counties before exhaustion."
                )
                sys.exit(2)

            calls_this_run = get_api_calls()
            _save_cumulative_credits(prior_calls + calls_this_run)
            prior_calls += calls_this_run

            county_chunks = sum(results.values())
            total_chunks += county_chunks

            print("\nMunicipality results:")
            for key, count in results.items():
                status = f"{count:,} chunks" if count > 0 else "FAILED"
                print(f"  {key:<40} {status}")

            _print_credit_summary(county, results, calls_this_run, prior_calls - calls_this_run)

        print(f"\n{'=' * 62}")
        print(f"  ALL {len(counties_filter)} COUNTIES COMPLETE")
        print(f"  Total chunks: {total_chunks:,}")
        print(f"  Total API calls used: {prior_calls} / {_NVIDIA_FREE_CREDITS}")
        print(f"{'=' * 62}")

    elif mode in ("--all", "--state", "--resume") and county_filter:
        # County-by-county manual ingestion
        from plotlot.core.errors import NvidiaCreditsExhaustedError
        from plotlot.ingestion.embedder import get_api_calls, reset_api_calls
        from plotlot.pipeline.ingest import ingest_county

        if not state_filter:
            print("Error: --county requires --state. Example: --state CA --county sacramento")
            sys.exit(1)

        reset_api_calls()
        prior_calls = _load_cumulative_credits()

        try:
            results = asyncio.run(ingest_county(state_filter, county_filter))
        except NvidiaCreditsExhaustedError as e:
            calls_this_run = get_api_calls()
            _save_cumulative_credits(prior_calls + calls_this_run)
            _print_credits_exhausted(str(e))
            sys.exit(2)

        calls_this_run = get_api_calls()
        _save_cumulative_credits(prior_calls + calls_this_run)

        print("\nMunicipality results:")
        for key, count in results.items():
            status = f"{count:,} chunks" if count > 0 else "FAILED"
            print(f"  {key:<40} {status}")

        _print_credit_summary(county_filter, results, calls_this_run, prior_calls)

    elif mode in ("--all", "--state", "--resume"):
        from plotlot.core.errors import NvidiaCreditsExhaustedError
        from plotlot.pipeline.ingest import ingest_all

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
            count = asyncio.run(ingest_municipality(key, state=state_filter))
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
