"""Extract verified DistrictDimensionalStandard rows from the INGESTED ordinance
corpus for Fort Lauderdale — reading the real pipe-delimited table chunks that
already exist in ordinance_chunks (no re-scraping needed).

Fort Lauderdale is the one municipality whose dimensional tables survived
ingestion with pipe structure (the Jina path mangled others). This script
reads those real chunks, parses the labeled rows, and upserts verified rows
into district_dimensional_standards with source_section_id pointing at the
real ordinance_chunks.id.

Run:
    uv run python scripts/extract_ftl_dimensional_standards.py
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict

from sqlalchemy import text

from plotlot.domain.dimensional_standard import DistrictDimensionalStandard
from plotlot.storage.db import get_session, init_db
from plotlot.storage.dimensional_standards import store_dimensional_standards


# Map dimensional-table row labels (as they appear in the chunk text) to
# canonical fields on DistrictDimensionalStandard. These are the labels
# Fort Lauderdale's §47-5.3x tables use.
_ROW_LABEL_MAP = {
    "maximum density": "max_density_units_per_acre",
    "minimum lot size": "min_lot_area_sqft",
    "minimum lot width": "min_lot_width_ft",
    "maximum structure height": "max_height_ft",
    "minimum front yard": "setback_front_ft",
    "minimum front setback": "setback_front_ft",
    "minimum side yard": "setback_side_ft",
    "minimum side setback": "setback_side_ft",
    "minimum rear yard": "setback_rear_ft",
    "minimum rear setback": "setback_rear_ft",
    "maximum lot coverage": "max_lot_coverage_pct",
    "floor area ratio": "far",
    "maximum floor area ratio": "far",
}

# Numeric extraction: pull the first number (with decimals) from a cell.
_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _parse_number(cell: str) -> float | None:
    """Extract the first numeric value from a cell (handles '8.0 du/net ac.',
    '6,000 sq. ft.', '25 ft.', etc.)."""
    cell = cell.replace(",", "")
    m = _NUM_RE.search(cell)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _classify_row(label: str) -> str | None:
    """Map a row label to a canonical field name."""
    key = re.sub(r"\s+", " ", label.lower().strip())
    for prefix, field in _ROW_LABEL_MAP.items():
        if key.startswith(prefix):
            return field
    return None


def _extract_districts_from_chunk(chunk_text: str) -> dict[str, dict[str, float]]:
    """Parse a dimensional-table chunk into {district_code: {field: value}}.

    The chunks are labeled rows: 'Requirements | RS-8 | RS-8A' as a header,
    then 'Maximum density | 8.0 du/net ac. | 8.0 du/net ac.' etc. We find the
    header row to get district codes, then map each data row's values to those
    districts by column.
    """
    lines = [ln.strip() for ln in chunk_text.splitlines() if ln.strip()]
    # find the header row (contains 'Requirements' or district codes)
    header_idx = None
    district_cols: list[str] = []
    for i, ln in enumerate(lines):
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.split("|")]
        # header row has district codes in columns 1+
        # District codes: RS-8, RM-15, RD-15, RC-15, RS-4.4, CC, CR, RAC, SRAC, etc.
        # Letters optionally followed by -digits (with optional decimal). Pure
        # 1-4 letter codes (CC, CR) are also valid. Reject prose cells.
        codes = [c for c in cells[1:]
                 if re.match(r"^[A-Z]{1,4}(-?\d+(?:\.\d+)?)?$", c) and len(c) <= 12]
        if len(codes) >= 1 and i < 10:
            header_idx = i
            district_cols = codes
            break
    if header_idx is None:
        return {}

    results: dict[str, dict[str, float]] = defaultdict(dict)
    for district in district_cols:
        results[district]  # init

    # parse data rows below the header
    for ln in lines[header_idx + 1 :]:
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.split("|")]
        if len(cells) < 2:
            continue
        label = cells[0]
        field = _classify_row(label)
        if not field:
            continue
        # map each value cell to its district column
        for i, val in enumerate(cells[1:]):
            if i >= len(district_cols):
                break
            district = district_cols[i]
            num = _parse_number(val)
            if num is not None:
                # keep the first non-null per field (some tables repeat cols)
                if field not in results[district]:
                    results[district][field] = num
    return dict(results)


async def extract_ftl() -> None:
    await init_db()
    session = await get_session()
    try:
        # find all FTL chunks with a dimensional-table title
        result = await session.execute(text("""
            SELECT id, section, section_title, chunk_text, source_url, scraped_at
            FROM ordinance_chunks
            WHERE municipality = 'Fort Lauderdale'
              AND (section_title ILIKE '%table of dimensional requirements%'
                   OR section_title ILIKE '%schedule of district regulations%')
            ORDER BY id
        """))
        chunks = result.all()
    finally:
        await session.close()

    print(f"Found {len(chunks)} dimensional-table chunks for Fort Lauderdale")
    all_rows: list[DistrictDimensionalStandard] = []
    seen: set[str] = set()
    for chunk_id, section, section_title, chunk_text, source_url, scraped_at in chunks:
        districts = _extract_districts_from_chunk(chunk_text)
        if not districts:
            continue
        for district_code, values in districts.items():
            if district_code in seen:
                continue
            if not any(k in values for k in ("max_density_units_per_acre", "min_lot_area_sqft")):
                continue
            seen.add(district_code)
            source_section_id = f"{section or section_title} (ordinance_chunks id={chunk_id})"
            row = DistrictDimensionalStandard(
                municipality="Fort Lauderdale",
                county="Broward",
                state="FL",
                district_code=district_code,
                min_lot_area_sqft=values.get("min_lot_area_sqft"),
                min_lot_width_ft=values.get("min_lot_width_ft"),
                setback_front_ft=values.get("setback_front_ft"),
                setback_side_ft=values.get("setback_side_ft"),
                setback_rear_ft=values.get("setback_rear_ft"),
                max_height_ft=values.get("max_height_ft"),
                max_lot_coverage_pct=values.get("max_lot_coverage_pct"),
                far=values.get("far"),
                max_density_units_per_acre=values.get("max_density_units_per_acre"),
                source_section_id=source_section_id,
                source_url=source_url or "",
            )
            all_rows.append(row)
            print(f"  {district_code:8} density={row.max_density_units_per_acre} "
                  f"lot={row.min_lot_area_sqft} front={row.setback_front_ft} "
                  f"rear={row.setback_rear_ft} far={row.far}")

    print(f"\nExtracted {len(all_rows)} verified FTL dimensional standards.")
    if all_rows:
        n = await store_dimensional_standards(all_rows)
        print(f"Stored {n} rows to district_dimensional_standards.")


if __name__ == "__main__":
    asyncio.run(extract_ftl())
