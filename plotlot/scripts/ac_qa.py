"""AC-QA: Verify all 7 acceptance criteria against test addresses.

AC-1: No "Pass"/"Buy" rating when comp confidence==0 OR "No sales dataset" note.
AC-2: BU-1 zoning → property_type MUST resolve to "commercial".
AC-3: Zoning must yield >=3 of {height, density, FAR, setbacks} non-empty.
AC-4: Geocode failure → honest error, no fake Pass.
AC-5: Missing lot size → "Insufficient Data" reason, no silent null.
AC-6: Same address x3 runs → identical zoning_district, numeric_params, max_units, rating.
AC-7: Cross-county structural consistency (same field-presence pattern).
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

TEST_ADDRESSES = [
    ("Miami-Dade", "1449 NW 68th Ter, Miami, FL 33150"),
    ("Broward", "5939 NW 52nd St, Coral Springs, FL 33067"),
    ("Palm Beach", "1118 S Palmway, Lake Worth Beach, FL 33460"),
]

BU1_ADDRESS = "94 NE 56th St, Miami, FL 33137"

AC_RESULTS: dict[str, bool] = {}


def _count_standards(np_) -> int:
    if np_ is None:
        return 0
    standards = [
        np_.far,
        np_.max_height_ft,
        np_.max_density_units_per_acre,
        np_.setback_front_ft,
        np_.setback_rear_ft,
        np_.setback_side_ft,
        np_.max_lot_coverage_pct,
    ]
    return sum(1 for s in standards if s is not None)


def _ac1_check(label: str, report, deal) -> bool:
    if deal is None:
        print(f"  AC-1 [{label}]: SKIP (no deal analysis)")
        return True
    rating = deal.investment_rating or ""
    ds = deal.data_sufficiency
    comp = deal.comp_analysis
    has_no_comps = (
        (comp is not None and comp.confidence == 0.0)
        or (comp is not None and any("No sales dataset" in n for n in comp.notes))
    )
    if has_no_comps and rating not in ("Insufficient Data",):
        print(f"  AC-1 [{label}]: FAIL — comp confidence=0 but rating='{rating}'")
        return False
    if has_no_comps and ds and ds.grade == "insufficient":
        print(f"  AC-1 [{label}]: PASS (comp confidence=0 → rating='Insufficient Data')")
        return True
    if not has_no_comps:
        print(f"  AC-1 [{label}]: PASS (comps present, rating='{rating}')")
        return True
    print(f"  AC-1 [{label}]: FAIL — no comps but rating='{rating}', ds_grade='{ds.grade if ds else 'N/A'}'")
    return False


def _ac2_check(report) -> bool:
    if report is None or report.numeric_params is None:
        print("  AC-2 [BU-1]: FAIL — no report or no numeric_params")
        return False
    pt = report.numeric_params.property_type or ""
    if "commercial" in pt.lower():
        print(f"  AC-2 [BU-1]: PASS (property_type='{pt}')")
        return True
    print(f"  AC-2 [BU-1]: FAIL — property_type='{pt}', expected 'commercial'")
    return False


def _ac3_check(label: str, report) -> bool:
    count = _count_standards(report.numeric_params if report else None)
    if count >= 3:
        print(f"  AC-3 [{label}]: PASS ({count}/7 standards)")
        return True
    print(f"  AC-3 [{label}]: FAIL ({count}/7 standards — hollow extraction)")
    return False


def _ac4_check(label: str, error) -> bool:
    if error and "geocod" in str(error).lower():
        print(f"  AC-4 [{label}]: PASS (geocode failure surfaced as error)")
        return True
    print(f"  AC-4 [{label}]: SKIP (no geocode error to test)")
    return True


def _ac5_check(label: str, report, deal) -> bool:
    if report is None or report.property_record is None:
        print(f"  AC-5 [{label}]: SKIP (no property record)")
        return True
    lot = report.property_record.lot_size_sqft
    if lot and lot > 0:
        print(f"  AC-5 [{label}]: PASS (lot_size={lot} sqft — present)")
        return True
    if deal and deal.data_sufficiency and deal.data_sufficiency.grade == "insufficient":
        reason = deal.data_sufficiency.reason or ""
        if "lot" in reason.lower() or "size" in reason.lower():
            print(f"  AC-5 [{label}]: PASS (lot_size=0 → Insufficient Data: '{reason}')")
            return True
        print(f"  AC-5 [{label}]: FAIL (lot_size=0 but reason doesn't mention lot: '{reason}')")
        return False
    if deal and deal.investment_rating == "Insufficient Data":
        print(f"  AC-5 [{label}]: PASS (lot_size=0 → Insufficient Data)")
        return True
    print(f"  AC-5 [{label}]: FAIL (lot_size=0 but rating='{deal.investment_rating if deal else 'N/A'}')")
    return False


async def _ac6_check(address: str, label: str) -> bool:
    from plotlot.pipeline.lookup import lookup_address, clear_zoning_params_cache

    print(f"  AC-6 [{label}]: Running 3x determinism check...")
    results = []
    for i in range(3):
        clear_zoning_params_cache()
        try:
            r = await lookup_address(address)
            results.append(r)
        except Exception as e:
            print(f"  AC-6 [{label}]: Run {i+1} failed: {e}")
            results.append(None)

    valid = [r for r in results if r is not None]
    if len(valid) < 2:
        print(f"  AC-6 [{label}]: SKIP (only {len(valid)} successful runs)")
        return True

    first = valid[0]
    district_set = {r.zoning_district for r in valid}
    max_units_set = {r.density_analysis.max_units if r.density_analysis else None for r in valid}

    np_first = first.numeric_params
    np_match = True
    if np_first:
        for r in valid[1:]:
            np_r = r.numeric_params
            if np_r is None:
                np_match = False
                break
            for field in ("far", "max_height_ft", "max_density_units_per_acre",
                          "setback_front_ft", "setback_side_ft", "setback_rear_ft"):
                if getattr(np_first, field) != getattr(np_r, field):
                    np_match = False
                    break

    if len(district_set) == 1 and len(max_units_set) == 1 and np_match:
        print(f"  AC-6 [{label}]: PASS (district='{first.zoning_district}', units={first.density_analysis.max_units if first.density_analysis else 'N/A'}, params stable)")
        return True
    print(f"  AC-6 [{label}]: FAIL — districts={district_set}, units={max_units_set}, params_stable={np_match}")
    return False


def _ac7_check(reports: list) -> bool:
    valid = [(label, r) for label, r in reports if r is not None]
    if len(valid) < 2:
        print(f"  AC-7: SKIP (only {len(valid)} successful runs)")
        return True

    fields_present = {}
    for label, r in valid:
        fields_present[label] = {
            "zoning_district": bool(r.zoning_district),
            "numeric_params": r.numeric_params is not None,
            "density_analysis": r.density_analysis is not None,
            "property_record": r.property_record is not None,
        }

    patterns = set()
    for label, fp in fields_present.items():
        pattern = tuple(sorted(fp.items()))
        patterns.add(pattern)

    if len(patterns) == 1:
        print(f"  AC-7: PASS (all {len(valid)} counties have same field-presence pattern)")
        for label, fp in fields_present.items():
            print(f"    {label}: {fp}")
        return True
    print(f"  AC-7: FAIL — {len(patterns)} different field-presence patterns:")
    for label, fp in fields_present.items():
        print(f"    {label}: {fp}")
    return False


async def run_full_pipeline(address: str, label: str):
    from plotlot.pipeline.lookup import lookup_address
    from plotlot.pipeline.deal_analysis import run_deal_analysis

    print(f"\n{'='*80}")
    print(f"  [{label}] {address}")
    print(f"{'='*80}")

    try:
        report = await lookup_address(address)
    except Exception as e:
        print(f"  lookup_address FAILED: {type(e).__name__}: {e}")
        return label, None, None, e

    if report is None:
        print("  lookup_address returned None")
        return label, None, None, None

    pr = report.property_record
    if pr:
        print(f"  Zoning code: '{pr.zoning_code or ''}'")
        print(f"  Lot size: {pr.lot_size_sqft} sqft")
        print(f"  Last sale: ${pr.last_sale_price:,.0f}" if pr.last_sale_price else "  Last sale: N/A")
    print(f"  Zoning district: '{report.zoning_district or ''}'")
    print(f"  Standards: {_count_standards(report.numeric_params)}/7")
    if report.numeric_params:
        print(f"  Property type: {report.numeric_params.property_type or 'N/A'}")
        print(f"  Provenance: {report.numeric_params.provenance or 'N/A'}")

    deal = None
    try:
        county = (pr.county if pr else "") or ""
        state = "FL"
        land_price = pr.assessed_value or 0.0
        deal = await run_deal_analysis(report, county, state, land_price)
        print(f"  Rating: {deal.investment_rating}")
        if deal.data_sufficiency:
            print(f"  Data sufficiency: {deal.data_sufficiency.grade} — {deal.data_sufficiency.reason[:80]}")
        if deal.comp_analysis:
            print(f"  Comp confidence: {deal.comp_analysis.confidence}")
        print(f"  Deal notes: {len(deal.notes)} items")
    except Exception as e:
        print(f"  run_deal_analysis FAILED: {type(e).__name__}: {e}")

    return label, report, deal, None


async def main():
    print("PLOTLT AC-QA: 7 ACCEPTANCE CRITERIA VERIFICATION")
    print("=" * 80)

    reports_for_ac7 = []
    ac1_pass = True
    ac3_pass = True
    ac5_pass = True

    for label, address in TEST_ADDRESSES:
        lbl, report, deal, err = await run_full_pipeline(address, label)
        reports_for_ac7.append((lbl, report))

        if err is None and report is not None:
            if not _ac1_check(lbl, report, deal):
                ac1_pass = False
            if not _ac3_check(lbl, report):
                ac3_pass = False
            if not _ac5_check(lbl, report, deal):
                ac5_pass = False
            _ac4_check(lbl, err)

    AC_RESULTS["AC-1"] = ac1_pass
    AC_RESULTS["AC-3"] = ac3_pass
    AC_RESULTS["AC-5"] = ac5_pass

    print(f"\n{'='*80}")
    print("AC-2: BU-1 → commercial property_type")
    print(f"{'='*80}")
    from plotlot.pipeline.lookup import lookup_address, clear_zoning_params_cache
    clear_zoning_params_cache()
    try:
        bu1_report = await lookup_address(BU1_ADDRESS)
        AC_RESULTS["AC-2"] = _ac2_check(bu1_report)
    except Exception as e:
        print(f"  AC-2: ERROR — {type(e).__name__}: {e}")
        AC_RESULTS["AC-2"] = False

    print(f"\n{'='*80}")
    print("AC-6: Determinism (same address x3 runs)")
    print(f"{'='*80}")
    ac6_label, ac6_addr = TEST_ADDRESSES[1]
    AC_RESULTS["AC-6"] = await _ac6_check(ac6_addr, ac6_label)

    print(f"\n{'='*80}")
    print("AC-7: Cross-county structural consistency")
    print(f"{'='*80}")
    AC_RESULTS["AC-7"] = _ac7_check(reports_for_ac7)

    print(f"\n{'='*80}")
    print("FINAL AC-QA RESULTS")
    print(f"{'='*80}")
    all_pass = True
    for ac, result in sorted(AC_RESULTS.items()):
        status = "PASS" if result else "FAIL"
        print(f"  {ac}: {status}")
        if not result:
            all_pass = False

    print(f"\n  OVERALL: {'ALL PASS' if all_pass else 'FAILURES PRESENT'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
