"""Populate the typed dimensional-standards table from ingested ordinance text.

**The missing link.** Every other piece of the deterministic density path was
already built and wired: ``extract_dimensional_standards`` (tables),
``store_dimensional_standards`` (persistence), ``get_dimensional_standard``
(query), and ``lookup.py`` calling it *before* LLM extraction and preferring its
result. But nothing ever called the extractor, so
``district_dimensional_standards`` held **zero rows for every municipality**.
``get_dimensional_standard`` returned ``None`` on every lookup, the code fell
through to LLM extraction every time, and the density inputs were re-derived by
a model on each run — which is why the same parcel returned 7 units on one run
and 0 on the next.

This module closes that gap: ordinance chunks in, typed rows out, persisted.

**Some cities cannot be made deterministic from ordinance text at all**, and that
is a data-sourcing gap rather than a missing pattern. Recorded here so the
investigation is not repeated:

* **Carlsbad** — the minimum lot area is keyed on the General Plan *land use
  designation*, not the zone. One zone code carries three different answers:
  "the minimum required area of a lot in the R-1 zone, when the zone implements
  the R1.5 / R-4 / R-8 land use designation" → 21,780 / 7,500 / 6,000 sqft. R-A
  and RD-M behave the same way; R-E is "determined by average natural slope"; E-A
  defers to "the number following the zoning symbol on the map". The zones that DO
  state one unconditional figure (R-2, R-3 at 7,500) are lot-size floors, not
  per-unit bases — R-3 is multiple-family and takes its density from the
  designation too. Unblocking Carlsbad needs the Carlsbad General Plan land use
  layer, not a better regex.
* **National City / San Marcos** — the chunker flattens their dimensional tables
  to positional columns ("Minimum lot area — 1: 15,000 SF; 2: 5,000 SF"), losing
  the header that maps a column to a district. Fixable upstream in chunking.
* **Imperial Beach** — states a minimum lot size that is NOT the per-unit basis
  (the R-3000 zone has a 6,000 sqft lot minimum).
* **Santee / La Mesa** — the only lot-size figures present are SB9 urban-lot-split
  minimums, a different rule from base zoning.
* **El Cajon** — promising but unvalidated: the code says the numeric suffix in a
  zone name IS the standard ("the numbers represent the minimum lot size in the
  single-family zones, and the density (minimum lot area per dwelling unit) in the
  multiple-family zones"), which would make the per-unit area derivable from the
  parcel's own zone code. The zone-name table (§17.15.010) is not captured in the
  ingested chunks, so the code list could not be confirmed.

**Corroboration is the verification.** ``VerificationStatus.VERIFIED`` means
"cross-checked against ingested source text". Chunks overlap heavily, so a
district's statement normally appears in several of them. Agreement across every
occurrence is the cross-check; a district whose occurrences DISAGREE is excluded
rather than resolved arbitrarily. A wrong deterministic row is worse than no row
— it converts a visibly-flaky number into a confidently wrong one.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import func, select

from plotlot.domain.dimensional_standard import (
    DistrictDimensionalStandard,
    VerificationStatus,
    extract_dimensional_standards,
    extract_dimensional_standards_from_prose,
)
from plotlot.storage.db import get_session
from plotlot.storage.dimensional_standards import store_dimensional_standards
from plotlot.storage.models import DistrictDimensionalStandardORM, OrdinanceChunk

logger = logging.getLogger(__name__)

# "18 du/acre", "24 dwelling units per net acre" — a density-governed district.
_DENSITY_TOKEN_RE = re.compile(
    r"\b(?:du|dwelling\s+units?)\s*(?:/|per\s+)\s*(?:net\s+|gross\s+)?ac(?:re)?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StandardsExtractionReport:
    """What an extraction run found — enough to audit it without re-running."""

    municipality: str
    chunks_scanned: int = 0
    districts_found: int = 0
    rows_written: int = 0
    #: Districts whose occurrences disagreed; excluded, never guessed at.
    conflicted: tuple[str, ...] = ()
    #: Districts governed by a du/acre density we could not capture; excluded,
    #: because their min-lot-area is a lot-size floor, NOT a per-unit basis.
    density_governed: tuple[str, ...] = ()
    #: district_code -> value, for spot-checking against the code.
    values: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.districts_found > 0

    def summary(self) -> str:
        head = (
            f"{self.municipality}: {self.districts_found} districts from "
            f"{self.chunks_scanned} chunks, {self.rows_written} rows written"
        )
        if self.conflicted:
            head += f"; EXCLUDED (conflicting values): {', '.join(self.conflicted)}"
        if self.density_governed:
            head += f"; EXCLUDED (du/acre governed): {', '.join(self.density_governed)}"
        return head


async def extract_standards_for_municipality(
    municipality: str,
    *,
    state: str = "",
    county: str = "",
) -> tuple[list[DistrictDimensionalStandard], StandardsExtractionReport]:
    """Read a municipality's ingested chunks and derive typed standards.

    Runs BOTH extractors over every chunk: the markdown-table one (codifier-served
    cities) and the prose one (PDF-scraped cities such as San Diego, which has no
    tables at all). A city may legitimately yield rows from either or both.

    Pure read — nothing is persisted here. See ``backfill_dimensional_standards``.
    """
    session = await get_session()
    try:
        stmt = select(
            OrdinanceChunk.chunk_text,
            OrdinanceChunk.section,
            OrdinanceChunk.county,
        ).where(OrdinanceChunk.municipality == municipality)
        chunks = (await session.execute(stmt)).all()
    finally:
        await session.close()

    if not chunks:
        return [], StandardsExtractionReport(municipality=municipality)

    resolved_county = county or (chunks[0][2] or "")

    # district_code -> {per_unit_sqft: [source_section, ...]}
    #
    # Corroboration keys on the DERIVED per-unit area, not on the raw field,
    # because a district may be stated as an area in one code and as a du/acre
    # density in another. Per-unit area is the single quantity both reduce to,
    # so agreement can be checked across the two encodings.
    observations: dict[str, dict[float, list[str]]] = {}
    # The row backing each (code, value), so the original encoding is persisted.
    representative: dict[tuple[str, float], DistrictDimensionalStandard] = {}
    # Districts whose source line states a du/acre density we did not capture.
    density_governed: set[str] = set()

    for text, section, _ in chunks:
        if not text:
            continue
        section_id = section or ""
        rows: list[DistrictDimensionalStandard] = []
        if "|" in text:
            rows.extend(
                extract_dimensional_standards(
                    text,
                    municipality=municipality,
                    county=resolved_county,
                    state=state,
                    source_section_id=section_id,
                    source_url="",
                )
            )
        rows.extend(
            extract_dimensional_standards_from_prose(
                text,
                municipality=municipality,
                county=resolved_county,
                state=state,
                source_section_id=section_id,
            )
        )
        for row in rows:
            value = row.to_numeric_zoning_params().min_lot_area_per_unit_sqft
            if value is None or value <= 0:
                # Table rows may carry only setbacks/height. Those are useful but
                # they are not what gates the unit count, and a row with no area
                # basis cannot be corroborated on the dimension that matters.
                continue

            # A minimum LOT SIZE is only a per-unit basis in a one-unit-per-lot
            # district. In a multi-family zone the governing rule is du/acre and
            # the lot minimum is merely a floor on subdividing. Escondido states
            # `| R-3 | 6,000 | 60 | 18 du/acre |` — storing 6,000 as the per-unit
            # area computes 4 units on a 24,000 sqft lot where the ordinance
            # allows 9. So when the district's own source line advertises a
            # du/acre density that the extractor did NOT capture, exclude it: we
            # have proof the area alone is the wrong basis.
            if row.max_density_units_per_acre is None and _states_density_for(
                text, row.district_code
            ):
                density_governed.add(row.district_code)
                continue

            observations.setdefault(row.district_code, {}).setdefault(value, []).append(section_id)
            representative.setdefault((row.district_code, value), row)

    verified: list[DistrictDimensionalStandard] = []
    conflicted: list[str] = []
    for code, by_value in sorted(observations.items()):
        if code in density_governed:
            # Seen safely in one chunk but density-governed in another — the
            # unsafe reading wins, because one proof that area is the wrong basis
            # is enough to disqualify the district.
            continue
        if len(by_value) > 1:
            # Two different numbers for one district. Do not pick one.
            conflicted.append(code)
            logger.warning(
                "Dimensional standard conflict for %s/%s: %s — excluded",
                municipality,
                code,
                {v: len(s) for v, s in by_value.items()},
            )
            continue
        value, sections = next(iter(by_value.items()))
        source = representative[(code, value)]
        verified.append(
            DistrictDimensionalStandard(
                municipality=municipality,
                county=resolved_county,
                state=state,
                district_code=code,
                # Persist the ordinance's own encoding, not the derived value.
                min_lot_area_sqft=source.min_lot_area_sqft,
                max_density_units_per_acre=source.max_density_units_per_acre,
                source_section_id=sections[0],
                verification_status=VerificationStatus.VERIFIED,
            )
        )

    if density_governed:
        logger.warning(
            "Density-governed districts excluded for %s (min-lot-area is not a "
            "per-unit basis there): %s",
            municipality,
            ", ".join(sorted(density_governed)),
        )

    report = StandardsExtractionReport(
        municipality=municipality,
        chunks_scanned=len(chunks),
        districts_found=len(verified),
        conflicted=tuple(conflicted),
        density_governed=tuple(sorted(density_governed)),
        values={r.district_code: r.min_lot_area_sqft or 0.0 for r in verified},
    )
    return verified, report


def _states_density_for(text: str, district_code: str) -> bool:
    """True when a line naming ``district_code`` also states a du/acre density.

    Scoped to the line so a density elsewhere in the chunk (a neighbouring
    district's row, or prose about a different zone) does not disqualify a
    genuinely area-governed district.
    """
    needle = district_code.lower()
    for line in text.splitlines():
        low = line.lower()
        if needle in low and _DENSITY_TOKEN_RE.search(low):
            return True
    return False


@dataclass(frozen=True)
class CoverageGap:
    """A municipality with ingested ordinance text but no typed standards."""

    municipality: str
    chunk_count: int
    standard_count: int


async def check_standards_coverage() -> list[CoverageGap]:
    """Municipalities whose density still comes from the LLM, not from stored rows.

    **This is the alarm.** The original defect was not that extraction was hard —
    it was that the table sat empty for months while every layer above it behaved
    as though it were populated, and nothing anywhere said so. Filling the table
    for San Diego fixes San Diego; this function is what stops the same silence
    from returning for the next city ingested, or if a re-ingest ever lands
    chunks without standards.

    A municipality appearing here is not necessarily broken — it means its unit
    counts are LLM-derived and therefore free to vary run to run.
    """
    session = await get_session()
    try:
        chunk_rows = (
            await session.execute(
                select(OrdinanceChunk.municipality, func.count()).group_by(
                    OrdinanceChunk.municipality
                )
            )
        ).all()
        standard_rows = (
            await session.execute(
                select(DistrictDimensionalStandardORM.municipality, func.count()).group_by(
                    DistrictDimensionalStandardORM.municipality
                )
            )
        ).all()
        chunk_counts: dict[str, int] = {str(m): int(n) for m, n in chunk_rows}
        standard_counts: dict[str, int] = {str(m): int(n) for m, n in standard_rows}
    finally:
        await session.close()

    return [
        CoverageGap(
            municipality=muni,
            chunk_count=n,
            standard_count=standard_counts.get(muni, 0),
        )
        for muni, n in sorted(chunk_counts.items())
        if standard_counts.get(muni, 0) == 0
    ]


async def backfill_dimensional_standards(
    municipality: str,
    *,
    state: str = "",
    county: str = "",
    dry_run: bool = False,
) -> StandardsExtractionReport:
    """Extract and persist a municipality's typed standards.

    Safe to re-run: ``store_dimensional_standards`` upserts on
    (municipality, district_code).
    """
    rows, report = await extract_standards_for_municipality(
        municipality, state=state, county=county
    )
    if dry_run or not rows:
        logger.info("Standards extraction (dry-run=%s) — %s", dry_run, report.summary())
        return report

    written = await store_dimensional_standards(rows)
    final = StandardsExtractionReport(
        municipality=report.municipality,
        chunks_scanned=report.chunks_scanned,
        districts_found=report.districts_found,
        rows_written=written,
        conflicted=report.conflicted,
        values=report.values,
    )
    logger.info("Standards extraction — %s", final.summary())
    return final


def main() -> None:
    """``plotlot-standards [--check | --dry-run] [<municipality> ...]``

    ``--check`` lists municipalities whose density is still LLM-derived. Run it
    after any ingest; a city listed there produces unit counts that can vary
    between runs.
    """
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        prog="plotlot-standards",
        description="Extract typed district dimensional standards from ingested ordinances.",
    )
    parser.add_argument("municipalities", nargs="*", help="municipality names to backfill")
    parser.add_argument("--state", default="", help="two-letter state code")
    parser.add_argument("--county", default="", help="county name")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report municipalities with ordinance chunks but no typed standards",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="extract and report without persisting"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async def _run() -> int:
        if args.check or not args.municipalities:
            gaps = await check_standards_coverage()
            if not gaps:
                print("All ingested municipalities have typed dimensional standards.")
                return 0
            print(
                f"{len(gaps)} municipalities have ordinance chunks but NO typed "
                "standards — their unit counts are LLM-derived and may vary run to run:"
            )
            for gap in gaps:
                print(f"   {gap.municipality:<32} {gap.chunk_count:>6} chunks")
            return 1

        for name in args.municipalities:
            report = await backfill_dimensional_standards(
                name, state=args.state, county=args.county, dry_run=args.dry_run
            )
            print(report.summary())
            for code, value in sorted(report.values.items()):
                print(f"   {code:<12} {value:>10,.0f} sqft/unit")
        return 0

    raise SystemExit(asyncio.run(_run()))
