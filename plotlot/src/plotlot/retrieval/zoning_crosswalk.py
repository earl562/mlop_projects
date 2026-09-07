"""GIS zoning-code → ordinance district-code crosswalk.

The two data tracks PlotLot joins use DIFFERENT vocabularies for the same
zoning district:

  Track 1 (county GIS layers)   →  the map label, e.g. ``"RS20"``
  Track 2 (ingested ordinance)  →  the adopted code-book label, e.g. ``"R-E"``

A hybrid search for ``"RS20"`` then matches no ordinance text — the two strings
share no lexical or semantic overlap — so a parcel returns its zoning code but
no dimensional standards, EVEN WHEN the ordinance is fully ingested. (Verified
case: Clark County, NV — the GIS layer reports ``RS20`` but Title 30 only ever
uses ``R-E`` for that district.)

This module normalizes a GIS zoning code to the ordinance district code used in
the code book, per jurisdiction, BEFORE the ordinance search runs. When no
crosswalk entry exists it returns the original code unchanged, so jurisdictions
without a mapping keep working exactly as before — the crosswalk only ever adds
coverage, never removes it.

Adding a jurisdiction is one dict entry: ``(STATE, JURISDICTION) -> {gis: ord}``.
Only VERIFIED mappings belong here; each entry documents how it was confirmed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Crosswalk table ───────────────────────────────────────────────────────────
#
# Keyed by (STATE_UPPER, JURISDICTION_UPPER). JURISDICTION is the county or
# municipality with the trailing "County" stripped — so "Clark County" and
# "Clark" both resolve to the "CLARK" table. GIS codes are stored in a normalized
# form (uppercase, separators removed) so "RS-20", "rs20", "RS 20" all match the
# "RS20" key; ordinance values are stored verbatim because they are what we feed
# the search (the hyphen in "R-E" matters for keyword/zone-code matching).

_CROSSWALK: dict[tuple[str, str], dict[str, str]] = {
    # Clark County, NV — Title 30 (Municode: library.municode.com/nv/clark_county).
    # The GIS layer labels single-family districts "RS{N}" where N is the minimum
    # lot size in THOUSANDS of square feet; the ordinance uses descriptive letter
    # codes. Mapping verified against Title 30 Table 30.40-1 by the min-lot anchor:
    #   R-U = 80,000 sqft, R-A = 40,000, R-E = 20,000, R-D = 10,000.
    # RS20 → R-E is the field-observed, confirmed case (2975 Montessouri St);
    # the RS80/RS40/RS10 siblings follow the same documented lot-area convention.
    ("NV", "CLARK"): {
        "RS80": "R-U",
        "RS40": "R-A",
        "RS20": "R-E",
        "RS10": "R-D",
    },
}


@dataclass(frozen=True)
class CrosswalkResult:
    """Outcome of translating a GIS zoning code to its ordinance district code."""

    gis_code: str
    """The original GIS code, e.g. ``"RS20"`` (empty if none was supplied)."""

    ordinance_code: str
    """The code to search the ordinance with — the mapped value when matched,
    otherwise the original GIS code unchanged."""

    matched: bool
    """True when a crosswalk entry was applied (GIS and ordinance codes differ)."""

    note: str = ""
    """Short human-readable explanation, for logging and agent guidance."""

    @property
    def search_code(self) -> str:
        """The code to use as the ordinance search query and zone-code boost."""
        return self.ordinance_code or self.gis_code


def _normalize_code(code: str) -> str:
    """Uppercase and strip separators so ``"RS-20"``/``"rs20"`` → ``"RS20"``."""
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def _normalize_jurisdiction(name: str) -> str:
    """Strip a trailing ``County`` and uppercase: ``"Clark County"`` → ``"CLARK"``."""
    label = re.sub(r"\bcounty\b", "", name or "", flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", label).strip().upper()


def crosswalk_zoning_code(
    gis_code: str,
    *,
    state: str = "",
    county: str = "",
    municipality: str = "",
) -> CrosswalkResult:
    """Translate a GIS zoning code to its ordinance district code.

    Resolution tries the (state, municipality) table first, then (state, county),
    so a city-specific mapping can override a county default. Matching is
    case-insensitive and tolerant of separator/format noise. When no entry
    exists the original code is returned unchanged (``matched=False``).

    Args:
        gis_code:     The zoning code as reported by the GIS layer (e.g. "RS20").
        state:        Two-letter state code (e.g. "NV").
        county:       County name, with or without "County" (e.g. "Clark").
        municipality: Municipality name, if more specific than the county.

    Returns:
        A :class:`CrosswalkResult`.
    """
    code = (gis_code or "").strip()
    if not code:
        return CrosswalkResult(gis_code="", ordinance_code="", matched=False)

    state_key = (state or "").strip().upper()
    normalized = _normalize_code(code)

    if state_key:
        for juris in (municipality, county):
            juris_key = _normalize_jurisdiction(juris)
            if not juris_key:
                continue
            table = _CROSSWALK.get((state_key, juris_key))
            if not table:
                continue
            for raw_key, ordinance in table.items():
                if _normalize_code(raw_key) == normalized and ordinance:
                    return CrosswalkResult(
                        gis_code=code,
                        ordinance_code=ordinance,
                        matched=True,
                        note=(
                            f"GIS code '{code}' maps to ordinance district "
                            f"'{ordinance}' in {juris_key.title()}, {state_key}"
                        ),
                    )

    # No mapping — search the ordinance with the GIS code as-is (prior behavior).
    return CrosswalkResult(gis_code=code, ordinance_code=code, matched=False)
