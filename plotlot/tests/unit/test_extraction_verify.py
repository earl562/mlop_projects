"""Tests for deterministic verification of LLM-extracted zoning numbers."""

from dataclasses import dataclass

from plotlot.core.types import NumericZoningParams
from plotlot.pipeline.extraction_verify import (
    _MIN_LOT_PATTERNS,
    _ground,
    _ground_for_zone,
    _zone_expected_density,
    verify_numeric_params,
)


@dataclass
class _Chunk:
    """Minimal stand-in for a SearchResult."""

    chunk_text: str
    section: str = "Sec. 1"
    section_title: str = ""


def _results(text: str) -> list[_Chunk]:
    return [_Chunk(chunk_text=text)]


# Realistic ordinance snippet: density 29 du/ac, min lot 1,500 sqft/unit, FAR 1.5.
ORDINANCE = (
    "The RM-29 zone permits a maximum density of 29 dwelling units per acre. "
    "The minimum lot area per unit shall be 1,500 square feet. "
    "The maximum floor area ratio (FAR) is 1.5."
)


def _field(ver, name):
    return next(f for f in ver.fields if f.field == name)


class TestVerifiedPath:
    def test_matching_values_verified(self):
        params = NumericZoningParams(
            max_density_units_per_acre=29, min_lot_area_per_unit_sqft=1500, far=1.5
        )
        ver = verify_numeric_params(params, _results(ORDINANCE), zone_code="RM-29")
        assert _field(ver, "max_density_units_per_acre").status == "verified"
        assert _field(ver, "min_lot_area_per_unit_sqft").status == "verified"
        assert _field(ver, "far").status == "verified"
        assert ver.overall == "verified"
        assert ver.offer_is_provisional is False
        assert _field(ver, "max_density_units_per_acre").citation  # has evidence


class TestConflictPath:
    def test_misread_density_flagged_san_diego_style(self):
        """LLM reads 29 du/ac as 35 — source says 29. Must be a CONFLICT."""
        params = NumericZoningParams(max_density_units_per_acre=35)
        ver = verify_numeric_params(params, _results(ORDINANCE), zone_code="RM-29")
        density = _field(ver, "max_density_units_per_acre")
        assert density.status == "conflict"
        assert density.source_value == 29
        assert ver.overall == "conflict"
        assert ver.offer_is_provisional is True
        assert any("29" in w for w in ver.warnings)

    def test_source_has_value_llm_missed_it(self):
        params = NumericZoningParams(max_density_units_per_acre=None)
        ver = verify_numeric_params(params, _results(ORDINANCE))
        density = _field(ver, "max_density_units_per_acre")
        assert density.source_value == 29
        assert density.status == "conflict"


class TestUnverifiedPath:
    def test_no_source_corroboration(self):
        params = NumericZoningParams(max_density_units_per_acre=29)
        ver = verify_numeric_params(params, _results("This text says nothing about density."))
        density = _field(ver, "max_density_units_per_acre")
        assert density.status == "unverified"
        assert ver.offer_is_provisional is True

    def test_no_search_results(self):
        params = NumericZoningParams(max_density_units_per_acre=29)
        ver = verify_numeric_params(params, None)
        assert _field(ver, "max_density_units_per_acre").status == "unverified"

    def test_no_params(self):
        ver = verify_numeric_params(None, _results(ORDINANCE))
        assert ver.overall == "unverified"
        assert ver.warnings


class TestZonePrior:
    def test_self_describing_codes(self):
        assert _zone_expected_density("RM-25") == 25
        assert _zone_expected_density("RD-1.5") == 1.5
        assert _zone_expected_density("MF18") == 18

    def test_single_family_codes_have_no_density_prior(self):
        # R-1 means one unit per lot, not 1 du/acre — must not trigger the prior.
        assert _zone_expected_density("R-1") is None
        assert _zone_expected_density("RS-7") is None

    def test_density_far_from_zone_code_warns(self):
        # Source text (35) agrees with LLM but the RM-29 code implies ~29 → flag.
        text = "maximum density of 35 dwelling units per acre"
        params = NumericZoningParams(max_density_units_per_acre=35)
        ver = verify_numeric_params(params, _results(text), zone_code="RM-15")
        assert any("zone code" in w.lower() for w in ver.warnings)


# San Diego encodes density as lot-area-per-DU, not units/acre.
SD_FORWARD = "In the RM-3-7 zone, one dwelling unit is allowed per 1,000 square feet of lot area."
SD_REVERSE = "A minimum of 1,000 square feet of lot area per dwelling unit is required."


class TestSanDiegoLotAreaGrounding:
    def test_one_du_per_n_sqft_grounds_min_lot(self):
        params = NumericZoningParams(min_lot_area_per_unit_sqft=1000)
        ver = verify_numeric_params(params, _results(SD_FORWARD), zone_code="RM-3-7")
        ml = _field(ver, "min_lot_area_per_unit_sqft")
        assert ml.source_value == 1000
        assert ml.status == "verified"

    def test_reverse_phrasing_grounds_min_lot(self):
        params = NumericZoningParams(min_lot_area_per_unit_sqft=1000)
        ver = verify_numeric_params(params, _results(SD_REVERSE), zone_code="RM-3-7")
        assert _field(ver, "min_lot_area_per_unit_sqft").status == "verified"

    def test_spurious_density_flagged_but_offer_firm(self):
        """1233 Hueneme: LLM emits a junk 6 u/ac next to the real 1,000 sqft/unit.

        Min-lot-area grounds + verifies; the contradictory density is flagged a
        CONFLICT; but because the density limit IS corroborated via min-lot-area,
        the offer is no longer provisional.
        """
        params = NumericZoningParams(
            max_density_units_per_acre=6.0, min_lot_area_per_unit_sqft=1000
        )
        ver = verify_numeric_params(params, _results(SD_FORWARD), zone_code="RM-3-7")
        assert _field(ver, "min_lot_area_per_unit_sqft").status == "verified"
        assert _field(ver, "max_density_units_per_acre").status == "conflict"
        assert ver.offer_is_provisional is False
        assert ver.overall == "partial"


class TestDeterminism:
    def test_repeatable(self):
        params = NumericZoningParams(max_density_units_per_acre=35)
        runs = [
            verify_numeric_params(params, _results(ORDINANCE), "RM-29").overall for _ in range(20)
        ]
        assert all(r == runs[0] for r in runs)


# The actual San Diego §131.0406 RM density block — every RM zone in ONE chunk.
# This is the text that broke live grounding: a plain first-match grab returns
# RM-1-1's 3,000 sqft/DU, so RM-3-7's correct 1,000 looked like a conflict and the
# offer was wrongly marked provisional. Zone-aware grounding reads the right row.
SD_RM_TABLE = (
    "RM-1-1 permits a maximum density of 1 dwelling unit for each 3,000 square feet of lot area "
    "RM-1-2 permits a maximum density of 1 dwelling unit for each 2,500 square feet of lot area "
    "RM-1-3 permits a maximum density of 1 dwelling unit for each 2,000 square feet of lot area "
    "RM-2-4 permits a maximum density of 1 dwelling unit for each 1,750 square feet of lot area "
    "RM-2-5 permits a maximum density of 1 dwelling unit for each 1,500 square feet of lot area "
    "RM-2-6 permits a maximum density of 1 dwelling unit for each 1,250 square feet of lot area "
    "RM-3-7 permits a maximum density of 1 dwelling unit for each 1,000 square feet of lot area "
    "RM-3-8 permits a maximum density of 1 dwelling unit for each 800 square feet of lot area "
    "RM-3-9 permits a maximum density of 1 dwelling unit for each 600 square feet of lot area"
)


def test_plain_ground_grabs_first_zone_the_bug():
    # Documents the failure mode: without zone-awareness the first density wins.
    value, _ = _ground(SD_RM_TABLE, _MIN_LOT_PATTERNS)
    assert value == 3000.0  # RM-1-1, the WRONG zone


def test_ground_for_zone_reads_the_target_zone_row():
    assert _ground_for_zone(SD_RM_TABLE, _MIN_LOT_PATTERNS, "RM-3-7")[0] == 1000.0
    assert _ground_for_zone(SD_RM_TABLE, _MIN_LOT_PATTERNS, "RM-3-9")[0] == 600.0
    assert _ground_for_zone(SD_RM_TABLE, _MIN_LOT_PATTERNS, "RM-1-3")[0] == 2000.0


def test_ground_for_zone_absent_code_falls_back_to_none():
    # Not present → None so the caller falls back to the global first-match path.
    assert _ground_for_zone(SD_RM_TABLE, _MIN_LOT_PATTERNS, "RX-9-99")[0] is None
    assert _ground_for_zone(SD_RM_TABLE, _MIN_LOT_PATTERNS, "")[0] is None


def test_hueneme_rm37_verifies_firm_from_multizone_chunk():
    # The end-to-end regression: RM-3-7 + extracted 1,000 sqft/DU must VERIFY
    # (not conflict with RM-1-1's 3,000) and the offer must NOT be provisional.
    params = NumericZoningParams(min_lot_area_per_unit_sqft=1000.0)
    result = verify_numeric_params(params, _results(SD_RM_TABLE), "RM-3-7")
    min_lot = next(f for f in result.fields if f.field == "min_lot_area_per_unit_sqft")
    assert min_lot.status == "verified"
    assert min_lot.source_value == 1000.0
    assert result.offer_is_provisional is False


def test_wrong_zone_would_still_conflict():
    # Sanity: if the parcel were RM-3-9 (600) but the LLM extracted 1,000, that is
    # a genuine conflict — zone-awareness must not paper over real disagreements.
    params = NumericZoningParams(min_lot_area_per_unit_sqft=1000.0)
    result = verify_numeric_params(params, _results(SD_RM_TABLE), "RM-3-9")
    min_lot = next(f for f in result.fields if f.field == "min_lot_area_per_unit_sqft")
    assert min_lot.status == "conflict"
    assert min_lot.source_value == 600.0
