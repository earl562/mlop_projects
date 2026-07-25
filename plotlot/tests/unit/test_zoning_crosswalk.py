"""Unit tests for the GIS → ordinance zoning-code crosswalk.

The crosswalk bridges the vocabulary gap between Track 1 (county GIS layers,
e.g. "RS20") and Track 2 (ingested ordinance text, e.g. "R-E"). Without it a
hybrid search for the GIS code matches no ordinance text even when the code is
fully ingested.
"""

from __future__ import annotations

from plotlot.retrieval.zoning_crosswalk import CrosswalkResult, crosswalk_zoning_code


# ---------------------------------------------------------------------------
# Matched mappings (Clark County, NV — the verified case)
# ---------------------------------------------------------------------------


def test_clark_county_rs20_maps_to_r_e() -> None:
    """The field-observed case: GIS 'RS20' → ordinance 'R-E'."""
    result = crosswalk_zoning_code("RS20", state="NV", county="Clark")
    assert result.matched is True
    assert result.ordinance_code == "R-E"
    assert result.search_code == "R-E"
    assert result.gis_code == "RS20"
    assert "R-E" in result.note


def test_county_name_with_suffix_resolves() -> None:
    """'Clark County' resolves the same table as 'Clark'."""
    result = crosswalk_zoning_code("RS20", state="NV", county="Clark County")
    assert result.matched is True
    assert result.ordinance_code == "R-E"


def test_municipality_label_resolves_county_table() -> None:
    """The provider may label the jurisdiction 'Clark County' as the municipality."""
    result = crosswalk_zoning_code("RS20", state="NV", municipality="Clark County")
    assert result.matched is True
    assert result.ordinance_code == "R-E"


def test_rs_series_siblings_map_by_lot_area_anchor() -> None:
    """The documented RS{N}→R-series convention covers the lot-area siblings."""
    assert crosswalk_zoning_code("RS80", state="NV", county="Clark").ordinance_code == "R-U"
    assert crosswalk_zoning_code("RS40", state="NV", county="Clark").ordinance_code == "R-A"
    assert crosswalk_zoning_code("RS10", state="NV", county="Clark").ordinance_code == "R-D"


def test_match_is_format_and_case_tolerant() -> None:
    """'rs-20', 'RS 20', 'rs20' all normalize to the 'RS20' key."""
    for variant in ("rs20", "RS-20", "RS 20", "  Rs20 "):
        result = crosswalk_zoning_code(variant, state="nv", county="clark")
        assert result.matched is True, f"variant {variant!r} did not match"
        assert result.ordinance_code == "R-E"


# ---------------------------------------------------------------------------
# Unmatched paths — must pass the code through unchanged (no regression)
# ---------------------------------------------------------------------------


def test_unknown_code_passes_through_unchanged() -> None:
    """A code with no crosswalk entry is returned as-is, matched=False."""
    result = crosswalk_zoning_code("RS20", state="CA", county="Santa Clara")
    assert result.matched is False
    assert result.ordinance_code == "RS20"
    assert result.search_code == "RS20"


def test_known_county_but_unmapped_code_passes_through() -> None:
    """Within a mapped county, an unmapped code is still returned unchanged."""
    result = crosswalk_zoning_code("C-2", state="NV", county="Clark")
    assert result.matched is False
    assert result.search_code == "C-2"


def test_empty_code_returns_empty_unmatched() -> None:
    result = crosswalk_zoning_code("", state="NV", county="Clark")
    assert result.matched is False
    assert result.gis_code == ""
    assert result.search_code == ""


def test_missing_state_does_not_match() -> None:
    """State is required to disambiguate jurisdictions — no state, no match."""
    result = crosswalk_zoning_code("RS20", county="Clark")
    assert result.matched is False
    assert result.search_code == "RS20"


def test_result_is_frozen_dataclass() -> None:
    result = crosswalk_zoning_code("RS20", state="NV", county="Clark")
    assert isinstance(result, CrosswalkResult)
    try:
        result.ordinance_code = "X"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("CrosswalkResult should be immutable")
