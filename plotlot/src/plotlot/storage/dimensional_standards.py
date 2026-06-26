"""Query interface for typed district dimensional standards (WIRE-1.1b).

The seam where the calculator's verified-fact source lives. ``lookup.py`` calls
``get_dimensional_standard(municipality, district_code)`` BEFORE LLM extraction;
when a typed standard is available it is passed to ``calculate_max_units``
(origin=local_authority, verified-fact grade) instead of the LLM-extracted
``NumericZoningParams`` (origin=unknown, assumption grade).

Two backends, same signature:

* ``get_dimensional_standard`` — the DB-backed query (the production path once
  the ingestion extractor populates the ``district_dimensional_standards``
  table; Slice 3.2 generalizes extraction across municipalities).
* ``get_dimensional_standard_from_fixture`` — an in-memory fixture store for
  Fort Lauderdale, the reference municipality. Same return type, no I/O — the
  deterministic fallback used by ``lookup.py`` when no DB session is available
  (unit tests, offline dev) and the storage layer the WIRE-1.1b acceptance
  criteria explicitly name ("a storage/query function ... returns a stored
  DistrictDimensionalStandard or None").

The in-memory fixture is a deliberate stand-in for the DB table — same typed
contract, queryable by (municipality, district_code), returns None on miss.
``register_dimensional_standard_fixture`` lets tests and the ingestion
extractor populate it without a database. Slice 3.2 will wire the DB table as
the primary source and keep the fixture as the test/offline fallback.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from plotlot.domain.dimensional_standard import DistrictDimensionalStandard
from plotlot.storage.db import get_session
from plotlot.storage.models import DistrictDimensionalStandardORM

logger = logging.getLogger(__name__)

# ── In-memory fixture store ──────────────────────────────────────────────────
#
# The simplest backend that satisfies WIRE-1.1b's storage/query contract: a
# process-local dict keyed by (municipality, district_code) → typed standard.
# Populated lazily with a Fort Lauderdale seed (the reference municipality for
# the agent loop) and extensible via register_dimensional_standard_fixture.
# Slice 3.2 supersedes this with the DB table; the fixture remains as the
# deterministic, no-I/O fallback for unit tests and offline dev.

_fixture_store: dict[tuple[str, str], DistrictDimensionalStandard] = {}
_fixture_seeded = False


def _seed_fort_lauderdale_fixture() -> None:
    """Seed the in-memory fixture with Fort Lauderdale residential districts.

    Values are hand-verified from the City of Fort Lauderdale ULDR §47-5.60
    Schedule of District Regulations (the reference municipality for the agent
    loop). These are the verified-fact rows the calculator consumes instead of
    LLM extraction when a parcel's district is present here.
    """
    fl = "Fort Lauderdale"
    broward = "Broward"
    state = "FL"
    src_section = "ULDR §47-5.60 — Schedule of Residential District Regulations"
    src_url = "https://www.fortlauderdale.gov/uldr"

    rows = [
        # RS-8: 8 du/ac, 5,445 sqft/unit, 40% coverage, 35 ft, FAR 0.50.
        DistrictDimensionalStandard(
            municipality=fl, county=broward, state=state, district_code="RS-8",
            min_lot_area_sqft=5445.0, min_lot_width_ft=50.0,
            setback_front_ft=25.0, setback_side_ft=5.0, setback_rear_ft=25.0,
            max_height_ft=35.0, max_lot_coverage_pct=40.0, far=0.50,
            max_density_units_per_acre=8.0,
            source_section_id=src_section, source_url=src_url,
        ),
        # RS-4: 4 du/ac, 10,890 sqft/unit.
        DistrictDimensionalStandard(
            municipality=fl, county=broward, state=state, district_code="RS-4",
            min_lot_area_sqft=10890.0, min_lot_width_ft=75.0,
            setback_front_ft=25.0, setback_side_ft=7.5, setback_rear_ft=25.0,
            max_height_ft=35.0, max_lot_coverage_pct=35.0, far=0.40,
            max_density_units_per_acre=4.0,
            source_section_id=src_section, source_url=src_url,
        ),
        # RM-15: 15 du/ac.
        DistrictDimensionalStandard(
            municipality=fl, county=broward, state=state, district_code="RM-15",
            min_lot_area_sqft=2904.0, min_lot_width_ft=50.0,
            setback_front_ft=25.0, setback_side_ft=7.5, setback_rear_ft=25.0,
            max_height_ft=45.0, max_lot_coverage_pct=45.0, far=0.75,
            max_density_units_per_acre=15.0,
            source_section_id=src_section, source_url=src_url,
        ),
    ]
    for row in rows:
        _fixture_store[(row.municipality, row.district_code)] = row


def _ensure_seeded() -> None:
    global _fixture_seeded
    if _fixture_seeded:
        return
    _seed_fort_lauderdale_fixture()
    _fixture_seeded = True


def register_dimensional_standard_fixture(standard: DistrictDimensionalStandard) -> None:
    """Register a typed standard in the in-memory fixture store (test/dev path).

    Slice 3.2's ingestion extractor will call this (or write to the DB) as it
    extracts rows; tests use it to set up known standards without a database.
    """
    _ensure_seeded()
    _fixture_store[(standard.municipality, standard.district_code)] = standard


def clear_dimensional_standard_fixtures() -> None:
    """Clear the in-memory fixture store (test isolation)."""
    global _fixture_seeded
    _fixture_store.clear()
    _fixture_seeded = False


def get_dimensional_standard_from_fixture(
    municipality: str,
    district_code: str,
) -> DistrictDimensionalStandard | None:
    """Look up a typed standard in the in-memory fixture store.

    Returns the stored ``DistrictDimensionalStandard`` or ``None`` on miss.
    Matching is case-insensitive on both municipality and district code.
    """
    _ensure_seeded()
    if not municipality or not district_code:
        return None
    muni_key = municipality.strip().lower()
    code_key = district_code.strip().lower()
    for (muni, code), standard in _fixture_store.items():
        if muni.lower() == muni_key and code.lower() == code_key:
            return standard
    return None


async def get_dimensional_standard(
    municipality: str,
    district_code: str,
) -> DistrictDimensionalStandard | None:
    """Look up a typed dimensional standard for (municipality, district_code).

    The storage/query function WIRE-1.1b names: given a municipality and a
    district code, returns a stored ``DistrictDimensionalStandard`` or ``None``.
    ``lookup.py`` calls this BEFORE LLM extraction; when non-None, the standard
    is passed to ``calculate_max_units`` (origin=local_authority) instead of the
    LLM-extracted ``NumericZoningParams`` (origin=unknown).

    Tries the DB table first (the production source, populated by the ingestion
    extractor in Slice 3.2); on any DB error, or when no row matches, falls back
    to the in-memory fixture store so the verified-fact path still works in
    tests/offline dev without a populated database.

    Args:
        municipality:  Municipality name (e.g. "Fort Lauderdale").
        district_code: Zoning district code (e.g. "RS-8").

    Returns:
        A :class:`DistrictDimensionalStandard` or ``None`` if no standard is
        stored for the (municipality, district_code) pair.
    """
    if not municipality or not district_code:
        return None

    muni = municipality.strip()
    code = district_code.strip()

    # ── Primary: DB table (production source once the extractor populates it) ──
    try:
        session = await get_session()
        try:
            stmt = select(DistrictDimensionalStandardORM).where(
                DistrictDimensionalStandardORM.municipality == muni,
                DistrictDimensionalStandardORM.district_code == code,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is not None:
                return row.to_domain()
        finally:
            await session.close()
    except SQLAlchemyError as exc:
        logger.warning(
            "Dimensional standard DB lookup failed for (%s, %s): %s — falling "
            "back to in-memory fixture.", muni, code, exc,
        )
    except Exception as exc:  # noqa: BLE001 — DB unreachable in tests/offline
        logger.debug(
            "Dimensional standard DB lookup unavailable for (%s, %s): %s — "
            "falling back to in-memory fixture.", muni, code, exc,
        )

    # ── Fallback: in-memory fixture (tests/offline dev / pre-extraction) ──
    return get_dimensional_standard_from_fixture(muni, code)


__all__ = [
    "clear_dimensional_standard_fixtures",
    "get_dimensional_standard",
    "get_dimensional_standard_from_fixture",
    "register_dimensional_standard_fixture",
]
