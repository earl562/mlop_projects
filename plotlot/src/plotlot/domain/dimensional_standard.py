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
# Prose extraction (PDF-scraped codes with no tables)
# ---------------------------------------------------------------------------
#
# `extract_dimensional_standards` above requires a pipe-delimited markdown table.
# That covers codifier-served cities, but it cannot read a scraped PDF: San Diego
# has 2,910 ingested chunks and NOT ONE contains a pipe character. Eight of the
# twenty ingested municipalities are in the same position.
#
# San Diego states density as highly regular prose instead, one bullet per district:
#
#     • RM-3-7 permits a maximum density of 1 dwelling unit for each
#       1,000 square feet of lot area
#     • RT-1-1 requires minimum 3,500-square-foot lots
#
# Two properties of the scraped text drive the design:
#
# 1. **Sentences wrap**, so the number often sits on the following line. The text
#    is whitespace-normalised before matching so "for each\n1,000" joins up.
# 2. **PDF page furniture is injected mid-sentence** — a running header like
#    "Ch. Art. Div. 13 1 4 4 San Diego Municipal Code Chapter 13: Zones (3-2026)"
#    can land between "for each" and its number. The patterns therefore require
#    the number to follow the trigger phrase with only whitespace between, so
#    furniture makes the match FAIL rather than bind the wrong number. Losing a
#    district is recoverable (chunks overlap, so a clean copy of the same
#    sentence almost always appears in a neighbouring chunk); binding a page
#    number as a density is not.

# A district code: RM-3-7, RT-1-1, RS-1-7, CC-3-4 ... letters then 1-3 numeric groups.
_PROSE_DISTRICT = r"[A-Z]{1,3}(?:-\d{1,3}){1,3}"
# Comma-grouped or bare integer.
_PROSE_SQFT = r"\d{1,3}(?:,\d{3})+|\d+"

# "RM-3-7 permits a maximum density of 1 dwelling unit for each 1,000 square feet
# of lot area". The gap between the code and the trigger is bounded and may not
# cross a bullet or section mark, so a truncated sentence cannot reach forward
# into the next district's number.
_PROSE_DENSITY_RE = re.compile(
    rf"(?P<code>{_PROSE_DISTRICT})\s+permits\s+[^•§]{{0,160}}?"
    rf"maximum\s+density\s+of\s+1\s+dwelling\s+unit\s+for\s+each\s+"
    rf"(?P<sqft>{_PROSE_SQFT})\s+square\s+feet\s+of\s+lot\s+area",
    re.IGNORECASE,
)

# "RT-1-1 requires minimum 3,500-square-foot lots" — a true minimum lot size.
_PROSE_MIN_LOT_RE = re.compile(
    rf"(?P<code>{_PROSE_DISTRICT})\s+requires\s+minimum\s+"
    rf"(?P<sqft>{_PROSE_SQFT})[-\s]square[-\s]foot\s+lots",
    re.IGNORECASE,
)

# Sanity bounds. A lot-area-per-unit outside this range is a misparse (a page
# number, a year, a dollar figure), not a zoning standard.
_MIN_PLAUSIBLE_SQFT = 100.0
_MAX_PLAUSIBLE_SQFT = 500_000.0

# Encinitas and Poway both state density in WORDS alongside a minimum lot size:
#
#   **R-3: Residential 3** is intended to provide for single-family detached
#   residential units with minimum lot sizes of 14,500 net square feet and
#   maximum densities of three units per net acre
#
#   The RS-4 residential single-family 4 zone is intended as an area for
#   single-family residential development on minimum lot sizes of 10,000 square
#   feet and maximum densities of four units per acre
#
# The DENSITY is captured rather than the lot size, for two reasons. It is the
# ordinance's own density rule, and the minimum lot size is a gross-area floor
# that can exceed it — Poway RS-2 states 20,000 sqft against a 2 du/net-acre
# density (21,780 sqft/unit), so treating the lot minimum as the per-unit basis
# would OVER-count units on a sub-acre parcel, the dangerous direction for a
# tool that sets a purchase ceiling.
#
# Small integer densities also round-trip exactly (43560/2, /3, /4, /5 are all
# whole numbers), so the float-precision hazard that rules density out for San
# Diego's per-unit-area statements does not apply here.
_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "sixteen": 16,
    "eighteen": 18,
    "twenty": 20,
    "twenty-four": 24,
    "thirty": 30,
}

_PROSE_WORDED_DENSITY_RE = re.compile(
    rf"(?P<code>{_PROSE_DISTRICT})\b[^.•§]{{0,220}}?"
    r"maximum\s+densit(?:y|ies)\s+of\s+(?P<n>[a-z-]+|\d{1,3})\s+units?\s+"
    r"per\s+(?:net\s+|gross\s+)?acre",
    re.IGNORECASE,
)

# A density above this is not a base residential zone in these codes.
_MAX_PLAUSIBLE_DU_ACRE = 200.0

# El Cajon puts the standard in the zone's own NAME, in its establishment-of-zones
# table (§17.15.010):
#
#   | RS-14   | Residential, Single-family, 14,000 square-foot |
#   | RM-2500 | Residential, Multi-family 2,500 square-foot    |
#
# The code says explicitly what those numbers mean: "the numbers represent the
# minimum lot size in the single-family zones, and the density (minimum lot area
# per dwelling unit) in the multiple-family zones". Both reduce to the same thing
# for the calculator — lot area per dwelling unit — so either row type is stored
# as `min_lot_area_sqft` (exact integers, no float round-trip).
#
# The descriptive name is what makes this safe. The CODE alone is ambiguous:
# RS-6 means 6,000 sqft while RM-2500 means 2,500, so inferring the value from
# the numeric suffix would have been wrong by three orders of magnitude for the
# RS zones. Requiring the spelled-out figure also drops RM-HR (High-Rise, no
# number) and every non-residential row rather than guessing at them.
_ZONE_NAME_TABLE_RE = re.compile(
    r"\|\s*(?P<code>[A-Z]{1,3}-[A-Z0-9]{1,5})\s*\|\s*"
    r"Residential[,\s]+(?:Single|Multi)-family[,\s]+"
    r"(?P<sqft>\d{1,3}(?:,\d{3})+|\d+)\s*square[-\s]foot",
    re.IGNORECASE,
)

# Oceanside names each district and states two densities in one sentence:
#
#   the Estate A (RE -A) District where the base density is 0.5 dwelling units per
#   gross acre and the maximum potential density is 0.9 dwelling units per gross acre
#
# **Only the BASE density is captured.** The "maximum potential" figure requires a
# density bonus or discretionary approval; it is not by-right, and using it would
# overstate what a buyer can build as of right — which flows straight into the
# purchase ceiling.
#
# District codes here carry LETTER suffixes (RE-A, RM-B, RH) rather than the
# numeric ones San Diego uses, and the PDF sprinkles stray spaces inside them
# ("RE -A", "single -family"), so the code allows optional whitespace around the
# hyphen and is normalised afterwards. The pattern is anchored on two separate
# cues — the literal word "District" and the phrase "base density is" — so a bare
# two-letter token cannot match on its own.
#
# The code is matched case-SENSITIVELY via a scoped `(?-i:...)` flag even though
# the surrounding phrase is case-insensitive. Without that, `[A-Z]` under
# re.IGNORECASE happily matches lowercase and the pattern binds the tail of an
# ordinary word — "...RESIDENTIAL District" yielded a district literally named
# "IAL". A minimum of two letters and a preceding non-letter guard finish the
# job: they reject the bare "B" in "Estate B District" (whose real code is the
# parenthesised RE-B) and the truncated "M-B".
_PROSE_BASE_DENSITY_RE = re.compile(
    r"(?<![A-Za-z])\(?\s*(?P<code>(?-i:[A-Z]{2,3}(?:\s*-\s*[A-Z0-9]{1,2})?))(?![A-Za-z])\s*\)?\s*"
    r"(?:District\b)?[^.]{0,80}?base\s+density\s+is\s+(?P<n>\d+(?:\.\d+)?)\s+"
    r"(?:dwelling\s+)?units?\s+per\s+(?:gross\s+|net\s+)?acre",
    re.IGNORECASE,
)


def extract_dimensional_standards_from_prose(
    text: str,
    *,
    municipality: str,
    county: str,
    state: str,
    source_section_id: str,
    source_url: str = "",
    verification_status: "VerificationStatus | None" = None,
) -> list[DistrictDimensionalStandard]:
    """Extract typed standards from ordinance PROSE (no table required).

    Returns one row per district statement found. The caller is expected to
    corroborate across chunks before trusting a value — see
    ``plotlot.ingestion.standards_extraction``.

    **Density is stored as ``min_lot_area_sqft``, deliberately, not as
    ``max_density_units_per_acre``.** "1 dwelling unit per N square feet" is a
    per-unit lot area, and ``_min_lot_area_per_unit()`` returns
    ``min_lot_area_sqft`` verbatim when no density is set — exact integer
    arithmetic. Converting to du/acre and back does NOT round-trip cleanly
    (1,750 → 43560/1750 → 1750.0000000000002), and the calculator FLOORS the
    result, so a lot that divides evenly would silently lose a unit:
    ``floor(7000 / 1000.0000000001) == 6``. Exactness matters more here than
    field-name tidiness, and ``_min_lot_area_per_unit`` is the only reader.
    """
    if not text:
        return []

    # Join wrapped lines so "for each\n1,000 square feet" reads as one sentence.
    flat = re.sub(r"\s+", " ", text)

    found: dict[str, float] = {}
    for pattern in (_PROSE_DENSITY_RE, _PROSE_MIN_LOT_RE, _ZONE_NAME_TABLE_RE):
        for m in pattern.finditer(flat):
            code = m.group("code").upper()
            sqft = _parse_number(m.group("sqft"))
            if sqft is None or not (_MIN_PLAUSIBLE_SQFT <= sqft <= _MAX_PLAUSIBLE_SQFT):
                continue
            # A district stated twice within ONE chunk with different values is
            # ambiguous; drop it rather than pick arbitrarily.
            if code in found and found[code] != sqft:
                found[code] = float("nan")
                continue
            found[code] = sqft

    # du/acre densities — a separate axis, so a district may legitimately appear
    # here and not above. Worded (Encinitas, Poway) and decimal base-density
    # (Oceanside) forms both land in this map.
    densities: dict[str, float] = {}
    for pattern in (_PROSE_WORDED_DENSITY_RE, _PROSE_BASE_DENSITY_RE):
        for m in pattern.finditer(flat):
            # Strip the stray spaces the PDF inserts inside codes ("RE -A").
            code = re.sub(r"\s+", "", m.group("code")).upper()
            raw = m.group("n").lower()
            value = float(_WORD_NUMBERS[raw]) if raw in _WORD_NUMBERS else _parse_number(raw)
            if value is None or not (0 < value <= _MAX_PLAUSIBLE_DU_ACRE):
                continue
            if code in densities and densities[code] != value:
                densities[code] = float("nan")
                continue
            densities[code] = value

    codes = sorted(set(found) | set(densities))
    rows: list[DistrictDimensionalStandard] = []
    for code in codes:
        sqft = found.get(code)
        density = densities.get(code)
        # Drop NaN-marked conflicts on either axis.
        if sqft is not None and sqft != sqft:
            continue
        if density is not None and density != density:
            continue
        # When a district states BOTH, the density is the ordinance's density rule
        # and the lot size is a floor. Keep the density and leave the area unset so
        # `_min_lot_area_per_unit` derives per-unit from the density rather than
        # from a lot minimum that can under-state it.
        if density is not None:
            sqft = None
        if sqft is None and density is None:
            continue
        rows.append(
            DistrictDimensionalStandard(
                municipality=municipality,
                county=county,
                state=state,
                district_code=code,
                min_lot_area_sqft=sqft,
                max_density_units_per_acre=density,
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
