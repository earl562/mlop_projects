"""Seed the live DB with verified South FL dimensional standards (Slice 3.2).

Real dimensional standards extracted from the INGESTED ordinance corpus
(ordinance_chunks table) — the authoritative source. Values verified against
the actual section text, not hand-entered guesses. See the verification log in
progress.txt (2026-06-26 3.2-correction) for the per-row source-section audit.

Fort Lauderdale values are read directly from the ordinance_chunks rows:
  * RS-8   → Sec. 47-5.31 (id 3755)
  * RS-4.4 → Sec. 47-5.30 (id 3752)  [NOTE: the real code is RS-4.4, not RS-4]
  * RM-15  → Sec. 47-5.34 (id 3764)

Run:
    uv run python scripts/seed_dimensional_standards.py

Idempotent: upserts on the (municipality, district_code) natural key.

This is the Slice 3.2 stand-in for governed ingestion (Phase 9): real verified
values loaded directly so the live-DB integration test has real data to query.
Miami + Hollywood values are still hand-entered (their ordinance corpus is not
yet ingested) and are marked assumption-grade via a source_section_id note;
Phase 9 ingestion will replace them with verified rows. The Fort Lauderdale
rows are verified against ingested ordinance text.
"""

from __future__ import annotations

import asyncio

from plotlot.domain.dimensional_standard import (
    DistrictDimensionalStandard,
    VerificationStatus,
)
from plotlot.storage.db import init_db
from plotlot.storage.dimensional_standards import store_dimensional_standards

ROWS: list[DistrictDimensionalStandard] = [
    # ── Fort Lauderdale (Broward County) — VERIFIED against ingested ordinance_chunks ──
    # Source: Sec. 47-5.31, ordinance_chunks.id=3755 (real ingested text).
    # Values read directly from the table: max density 8.0 du/net ac, min lot
    # 6,000 sf, max height 35 ft, min lot width 50 ft, min front yard 25 ft,
    # min side yard 5 ft, min rear yard 15 ft (25 ft only when abutting a
    # waterway), max lot coverage 50% (≤7,500 sf tier), FAR 0.75 (≤7,500 sf tier).
    DistrictDimensionalStandard(
        municipality="Fort Lauderdale",
        county="Broward",
        state="FL",
        district_code="RS-8",
        min_lot_area_sqft=6000,
        min_lot_width_ft=50,
        setback_front_ft=25,
        setback_side_ft=5,
        setback_rear_ft=15,
        max_height_ft=35,
        max_lot_coverage_pct=50,
        far=0.75,
        max_density_units_per_acre=8.0,
        source_section_id="Sec. 47-5.31 (ordinance_chunks id=3755)",
        source_url="https://www.fortlauderdale.gov/uldr",
        verification_status=VerificationStatus.VERIFIED,
    ),
    # Source: Sec. 47-5.30, ordinance_chunks.id=3752. NOTE: the real district
    # code is RS-4.4, NOT RS-4 (no RS-4 district exists in Fort Lauderdale).
    # Density 4.4 du/net ac, min lot 10,000 sf, height 35 ft, width 75 ft,
    # front 25 ft, side 10 ft, rear 15 ft, coverage 45%, FAR 0.75.
    DistrictDimensionalStandard(
        municipality="Fort Lauderdale",
        county="Broward",
        state="FL",
        district_code="RS-4.4",
        min_lot_area_sqft=10000,
        min_lot_width_ft=75,
        setback_front_ft=25,
        setback_side_ft=10,
        setback_rear_ft=15,
        max_height_ft=35,
        max_lot_coverage_pct=45,
        far=0.75,
        max_density_units_per_acre=4.4,
        source_section_id="Sec. 47-5.30 (ordinance_chunks id=3752)",
        source_url="https://www.fortlauderdale.gov/uldr",
        verification_status=VerificationStatus.VERIFIED,
    ),
    # Source: Sec. 47-5.34, ordinance_chunks.id=3764. Density 15 du/net ac,
    # min lot 5,000 sf, height 35 ft, width 50 ft, front 25 ft, side 5 ft,
    # rear 15 ft.
    DistrictDimensionalStandard(
        municipality="Fort Lauderdale",
        county="Broward",
        state="FL",
        district_code="RM-15",
        min_lot_area_sqft=5000,
        min_lot_width_ft=50,
        setback_front_ft=25,
        setback_side_ft=5,
        setback_rear_ft=15,
        max_height_ft=35,
        max_lot_coverage_pct=45,
        far=0.75,
        max_density_units_per_acre=15.0,
        source_section_id="Sec. 47-5.34 (ordinance_chunks id=3764)",
        source_url="https://www.fortlauderdale.gov/uldr",
        verification_status=VerificationStatus.VERIFIED,
    ),
    # ── Miami (Miami-Dade County) — NOT YET verified against ingested text ──
    # Miami-Dade ordinance corpus is not yet ingested in ordinance_chunks.
    # These are hand-entered (assumption-grade) pending Phase 9 ingestion;
    # source_section_id carries a STAGED note so they are not mistaken for
    # verified-fact rows. To be replaced when Miami-Dade Code Ch. 33 is ingested.
    DistrictDimensionalStandard(
        municipality="Miami",
        county="Miami-Dade",
        state="FL",
        district_code="R-1",
        min_lot_area_sqft=7500,
        min_lot_width_ft=75,
        setback_front_ft=25,
        setback_side_ft=7.5,
        setback_rear_ft=25,
        max_height_ft=35,
        max_lot_coverage_pct=40,
        far=0.50,
        max_density_units_per_acre=5.8,
        source_section_id="STAGED: Miami-Dade Code §33-3.1 (not yet ingested — assumption-grade)",
        source_url="https://www.miamidade.gov/library/codes/chapter33",
        verification_status=VerificationStatus.STAGED,
    ),
    DistrictDimensionalStandard(
        municipality="Miami",
        county="Miami-Dade",
        state="FL",
        district_code="R-3",
        min_lot_area_sqft=5000,
        min_lot_width_ft=50,
        setback_front_ft=15,
        setback_side_ft=5,
        setback_rear_ft=15,
        max_height_ft=45,
        max_lot_coverage_pct=50,
        far=0.80,
        max_density_units_per_acre=17.4,
        source_section_id="STAGED: Miami-Dade Code §33-3.1 (not yet ingested — assumption-grade)",
        source_url="https://www.miamidade.gov/library/codes/chapter33",
        verification_status=VerificationStatus.STAGED,
    ),
    DistrictDimensionalStandard(
        municipality="Miami",
        county="Miami-Dade",
        state="FL",
        district_code="R-4",
        min_lot_area_sqft=3750,
        min_lot_width_ft=40,
        setback_front_ft=15,
        setback_side_ft=5,
        setback_rear_ft=15,
        max_height_ft=60,
        max_lot_coverage_pct=55,
        far=1.20,
        max_density_units_per_acre=43.5,
        source_section_id="STAGED: Miami-Dade Code §33-3.1 (not yet ingested — assumption-grade)",
        source_url="https://www.miamidade.gov/library/codes/chapter33",
        verification_status=VerificationStatus.STAGED,
    ),
    # ── Hollywood (Broward County) — NOT YET verified against ingested text ──
    DistrictDimensionalStandard(
        municipality="Hollywood",
        county="Broward",
        state="FL",
        district_code="RS-5",
        min_lot_area_sqft=7500,
        min_lot_width_ft=60,
        setback_front_ft=25,
        setback_side_ft=7.5,
        setback_rear_ft=25,
        max_height_ft=35,
        max_lot_coverage_pct=40,
        far=0.50,
        max_density_units_per_acre=5.0,
        source_section_id="STAGED: Hollywood ULDR Art. 9 (not yet ingested — assumption-grade)",
        source_url="https://www.hollywoodfl.gov/uldr",
        verification_status=VerificationStatus.STAGED,
    ),
    DistrictDimensionalStandard(
        municipality="Hollywood",
        county="Broward",
        state="FL",
        district_code="RM-15",
        min_lot_area_sqft=3000,
        min_lot_width_ft=50,
        setback_front_ft=20,
        setback_side_ft=7.5,
        setback_rear_ft=20,
        max_height_ft=45,
        max_lot_coverage_pct=45,
        far=0.75,
        max_density_units_per_acre=15.0,
        source_section_id="STAGED: Hollywood ULDR Art. 9 (not yet ingested — assumption-grade)",
        source_url="https://www.hollywoodfl.gov/uldr",
        verification_status=VerificationStatus.STAGED,
    ),
    DistrictDimensionalStandard(
        municipality="Hollywood",
        county="Broward",
        state="FL",
        district_code="RM-25",
        min_lot_area_sqft=2000,
        min_lot_width_ft=40,
        setback_front_ft=15,
        setback_side_ft=5,
        setback_rear_ft=15,
        max_height_ft=65,
        max_lot_coverage_pct=55,
        far=1.50,
        max_density_units_per_acre=25.0,
        source_section_id="STAGED: Hollywood ULDR Art. 9 (not yet ingested — assumption-grade)",
        source_url="https://www.hollywoodfl.gov/uldr",
        verification_status=VerificationStatus.STAGED,
    ),
]


async def main() -> None:
    await init_db()
    n = await store_dimensional_standards(ROWS)
    print(f"Seeded {n} South FL dimensional standards to the live DB.")
    print("Trust boundary: 3 verified Fort Lauderdale rows; 6 staged Miami/Hollywood rows.")
    print("Municipalities: Fort Lauderdale, Miami, Hollywood (3 municipalities, 3 districts each).")


if __name__ == "__main__":
    asyncio.run(main())
