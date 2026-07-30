"""Typed extraction of district dimensional standards from ordinance tables.

Slice 1.1 spike: extract §47-5.60-style dimensional tables into typed rows so
the calculator reads verified-fact rows instead of LLM-extracted
NumericZoningParams at query time.

This is the verified-fact path: a district's setbacks/height/FAR/coverage/density
come from a typed row with provenance, not from an LLM re-parsing the table
on every analysis.

Slice 3.2 (review feedback): added VerificationStatus enum. Only VERIFIED rows
may be used as local_authority/verified-fact calculator input. STAGED rows
(assumption-grade, not yet cross-checked against ingested ordinance text) must
NOT become verified facts. The calculator + storage layer enforce this at read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from plotlot.core.types import NumericZoningParams


class VerificationStatus(str, Enum):
    """Whether a DistrictDimensionalStandard has been verified against the
    ingested ordinance corpus (ordinance_chunks. source text).

    Only VERIFIED rows may serve as local_authority/verified-fact calculator
    input. STAGED rows are assumption-grade (hand-entered or auto-extracted
    without cross-checking) and must never produce verified_fact claims.
    UNVERIFIED is the default for rows from new ingestion runs before QC.
    """

    VERIFIED = "verified"  # cross-checked against ingested source text — production-ready
    STAGED = "staged"  # assumption-grade, pending QC — never becomes verified_fact
    UNVERIFIED = "unverified"  # from a fresh ingestion run, not yet QC'd


# District code: 1-4 uppercase letters, optional hyphen/digits/suffix.
# Matches RS-1, RM-15, T6-80, RMM-25, B-2, etc.
_DISTRICT_CODE_RE = re.compile(r"\b([A-Z]{1,4}-?\d{1,3}(?:\.\d+)?(?:-[A-Z0-9]+)?)\b")

# Numeric value: integer or decimal, possibly comma-grouped.
# NOTE: callers must strip commas before matching (see _parse_number); the
# comma-group alternative is kept here for defense-in-depth.
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# Column header aliases → canonical field. The dimensional tables across
# publishers vary in wording ("Front Setback" vs "Front Yard" vs "Min Front");
# this map normalizes them.
_COLUMN_ALIASES = {
    "min lot area": "min_lot_area_sqft",
    "minimum lot area": "min_lot_area_sqft",
    "min lot width": "min_lot_width_ft",
    "minimum lot width": "min_lot_width_ft",
    "front setback": "setback_front_ft",
    "front yard": "setback_front_ft",
    "min front": "setback_front_ft",
    "side setback": "setback_side_ft",
    "side yard": "setback_side_ft",
    "min side": "setback_side_ft",
    "rear setback": "setback_rear_ft",
    "rear yard": "setback_rear_ft",
    "min rear": "setback_rear_ft",
    "max height": "max_height_ft",
    "maximum height": "max_height_ft",
    "max lot coverage": "max_lot_coverage_pct",
    "maximum lot coverage": "max_lot_coverage_pct",
    "lot coverage": "max_lot_coverage_pct",
    "far": "far",
    "floor area ratio": "far",
    "max density": "max_density_units_per_acre",
    "maximum density": "max_density_units_per_acre",
    "density": "max_density_units_per_acre",
}

_NUMERIC_FIELDS = frozenset(_COLUMN_ALIASES.values())


@dataclass(frozen=True, slots=True)
class DistrictDimensionalStandard:
    """A typed, provenance-backed dimensional standard for one zoning district.

    This is the verified-fact source for every zoning.* and standards.* claim.
    Produced at ingestion time from the ordinance's Schedule of District Regulations.
    """

    municipality: str
    county: str
    state: str
    district_code: str
    min_lot_area_sqft: float | None = None
    min_lot_width_ft: float | None = None
    setback_front_ft: float | None = None
    setback_side_ft: float | None = None
    setback_rear_ft: float | None = None
    max_height_ft: float | None = None
    max_lot_coverage_pct: float | None = None
    far: float | None = None
    max_density_units_per_acre: float | None = None
    source_section_id: str = ""
    source_url: str = ""
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_numeric_zoning_params(self) -> NumericZoningParams:
        """Round-trip to the calculator's input type.

        This is the seam where the verified-fact row replaces LLM extraction:
        calculate_max_units(consumes=DistrictDimensionalStandard.to_numeric_zoning_params())
        instead of calculate_max_units(consumes=LLM_extracted_params).
        """
        return NumericZoningParams(
            max_density_units_per_acre=self.max_density_units_per_acre,
            min_lot_area_per_unit_sqft=self._min_lot_area_per_unit(),
            far=self.far,
            max_lot_coverage_pct=self.max_lot_coverage_pct,
            max_height_ft=self.max_height_ft,
        )

    def _min_lot_area_per_unit(self) -> float | None:
        """Derive min_lot_area_per_unit from min_lot_area and max_density.

        If density (du/acre) is present: per_unit = 43560 / density.
        Else: fall back to the raw min_lot_area (single-unit districts).
        """
        if self.max_density_units_per_acre and self.max_density_units_per_acre > 0:
            return 43560.0 / self.max_density_units_per_acre
        return self.min_lot_area_sqft

    def is_verified_fact_source(self) -> bool:
        """Can this standard serve as a verified-fact calculator input?

        Only VERIFIED rows may produce local_authority/verified_fact claims.
        STAGED rows are assumption-grade (hand-entered, not cross-checked
        against ingested source text); UNVERIFIED rows are from a fresh
        ingestion run that hasn't been QC'd — neither may become verified facts.
        """
        return self.verification_status == VerificationStatus.VERIFIED


def extract_dimensional_standards(
    table_text: str,
    *,
    municipality: str,
    county: str,
    state: str,
    source_section_id: str,
    source_url: str,
    verification_status: "VerificationStatus | None" = None,
) -> list[DistrictDimensionalStandard]:
    """Extract typed DistrictDimensionalStandard rows from a markdown table.

    The table is expected to be the output of _normalize_zone_tables() (the
    codifier adapter's normalization step): a header row identifying columns
    by name, followed by one data row per district.

    Rows whose first cell isn't a recognizable district code are skipped
    (non-district header rows, prose, totals, etc.).
    """
    columns = _parse_column_headers(table_text)
    if not columns:
        return []

    rows: list[DistrictDimensionalStandard] = []
    for line in _table_data_lines(table_text):
        cells = _split_table_row(line)
        if len(cells) < 2:
            continue
        district_code = cells[0].strip().upper()
        if not _DISTRICT_CODE_RE.fullmatch(district_code):
            continue

        values = _map_cells_to_fields(cells, columns)
        rows.append(
            DistrictDimensionalStandard(
                municipality=municipality,
                county=county,
                state=state,
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
                source_url=source_url,
                verification_status=verification_status or VerificationStatus.UNVERIFIED,
            )
        )
    return rows


# ---------------------------------------------------------------------------


def _parse_column_headers(table_text: str) -> dict[int, str]:
    """Map column index → canonical field name from the header row.

    Returns {} if no recognizable dimensional column is found (so the caller
    treats the table as non-dimensional and returns no rows).
    """
    for line in _table_lines(table_text):
        if "|" not in line:
            continue
        cells = _split_table_row(line)
        # Skip the markdown separator row (|---|---|...)
        if all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells if c.strip()):
            continue
        headers = [_canonical_field(c.strip()) for c in cells]
        # First column is the district code, not a numeric field.
        if any(h in _NUMERIC_FIELDS for h in headers[1:]):
            return {i: h for i, h in enumerate(headers) if h}
        # If no header row, fall back to positional defaults.
    return {}


def _canonical_field(header: str) -> str:
    """Normalize a column header to a canonical field name, or '' if unknown."""
    key = re.sub(r"\s+", " ", header.lower().strip()).rstrip(")").strip()
    # Try exact alias match first.
    if key in _COLUMN_ALIASES:
        return _COLUMN_ALIASES[key]
    # Try prefix match (e.g. "Min Lot Area (sqft)" → "min lot area").
    for alias, field_name in _COLUMN_ALIASES.items():
        if key.startswith(alias):
            return field_name
    # "(sqft)" / "(ft)" / "(%)" / "(du/acre)" suffixes alone → skip.
    return ""


def _table_lines(table_text: str) -> list[str]:
    return [ln for ln in table_text.splitlines() if ln.strip()]


def _table_data_lines(table_text: str) -> list[str]:
    """Yield table rows that are data (skip header + separator)."""
    seen_header = False
    out: list[str] = []
    for line in _table_lines(table_text):
        if "|" not in line:
            continue
        cells = _split_table_row(line)
        if all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells if c.strip()):
            continue
        if not seen_header:
            seen_header = True
            continue
        out.append(line)
    return out


def _split_table_row(line: str) -> list[str]:
    """Split a markdown table row into cells, trimming the leading/trailing pipes."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [c.strip() for c in stripped.split("|")]


def _map_cells_to_fields(cells: list[str], columns: dict[int, str]) -> dict[str, float]:
    """Map data cells to {canonical_field: value} using the header→field map."""
    out: dict[str, float] = {}
    for idx, field_name in columns.items():
        if idx == 0 or idx >= len(cells):
            continue
        if field_name not in _NUMERIC_FIELDS:
            continue
        value = _parse_number(cells[idx])
        if value is not None:
            out[field_name] = value
    return out


def _parse_number(cell: str) -> float | None:
    """Parse a numeric value from a cell, handling commas and units."""
    m = _NUMBER_RE.search(cell.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None
