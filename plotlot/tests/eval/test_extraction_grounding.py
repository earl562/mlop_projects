"""Eval harness: deterministic grounding of zoning numbers against ordinance text.

This is the regression lock for the San Diego incident — a hallucinated
buildable-unit driver must be caught (flagged CONFLICT and made provisional)
rather than silently flowing into a confident offer price. Fully deterministic
(no live LLM), so it runs in CI on every push.

Each golden case carries the ordinance text, the zone code, and the correct
values. We assert: (1) the correct values verify, and (2) a planted misread of
the density driver is flagged.
"""

from dataclasses import dataclass

from plotlot.core.types import NumericZoningParams
from plotlot.pipeline.calculator import calculate_max_units
from plotlot.pipeline.extraction_verify import is_field_verified, verify_numeric_params


@dataclass
class _Chunk:
    chunk_text: str
    section: str = "Zoning Ordinance"
    section_title: str = ""


@dataclass
class GoldenCase:
    name: str
    zone_code: str
    text: str
    density: float
    min_lot: float | None = None
    far: float | None = None


# Hand-verified ordinance snippets across PlotLot's covered markets.
GOLDEN_CASES = [
    GoldenCase(
        name="san_diego_rm_multifamily",
        zone_code="RM-3-9",  # multi-segment SD code: digits are NOT density
        text=(
            "In the RM-3-9 zone, the maximum density is 43 dwelling units per acre. "
            "The minimum lot area per dwelling unit shall be 1,000 square feet."
        ),
        density=43,
        min_lot=1000,
    ),
    GoldenCase(
        name="self_describing_rm25",
        zone_code="RM-25",
        text=(
            "The RM-25 district permits a maximum density of 25 dwelling units per acre "
            "with a maximum floor area ratio (FAR) of 1.0."
        ),
        density=25,
        far=1.0,
    ),
    GoldenCase(
        name="miami_dade_rm",
        zone_code="RM-18",
        text=(
            "Maximum density: 18 units per acre. Minimum lot area per unit: 2,420 square feet. "
            "Maximum floor area ratio is 0.8."
        ),
        density=18,
        min_lot=2420,
        far=0.8,
    ),
]


class TestGroundingAccuracy:
    def test_correct_values_verify(self):
        for case in GOLDEN_CASES:
            params = NumericZoningParams(
                max_density_units_per_acre=case.density,
                min_lot_area_per_unit_sqft=case.min_lot,
                far=case.far,
            )
            ver = verify_numeric_params(params, [_Chunk(case.text)], case.zone_code)
            density = next(f for f in ver.fields if f.field == "max_density_units_per_acre")
            assert density.status == "verified", f"{case.name}: density should verify"
            assert density.source_value == case.density, f"{case.name}: grounded value wrong"
            assert not ver.offer_is_provisional, f"{case.name}: should not be provisional"


class TestHueneme1233Regression:
    """The exact production failure: San Diego RM-3-7, lot-area-per-DU table only.

    The LLM emitted a spurious 6 u/ac next to the real 1,000 sqft/unit. End to
    end the system must ground + verify min-lot-area, flag the junk density, keep
    the offer firm, and compute 6 units (not the 1 it produced in production).
    """

    LOT_SQFT = 6470.6
    TEXT = "In the RM-3-7 zone, one dwelling unit is allowed per 1,000 square feet of lot area."

    def test_grounds_min_lot_and_flags_spurious_density(self):
        params = NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=1000.0,
            far=1.25,
            min_unit_size_sqft=500.0,
        )
        ver = verify_numeric_params(params, [_Chunk(self.TEXT)], "RM-3-7")
        assert is_field_verified(ver, "min_lot_area_per_unit_sqft")
        assert not is_field_verified(ver, "max_density_units_per_acre")
        assert ver.offer_is_provisional is False  # density limit corroborated

    def test_calculator_yields_6_units(self):
        params = NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=1000.0,
            far=1.25,
            min_unit_size_sqft=500.0,
        )
        ver = verify_numeric_params(params, [_Chunk(self.TEXT)], "RM-3-7")
        result = calculate_max_units(
            self.LOT_SQFT,
            params,
            density_verified=is_field_verified(ver, "max_density_units_per_acre"),
            min_lot_area_verified=is_field_verified(ver, "min_lot_area_per_unit_sqft"),
        )
        assert result.max_units == 6


class TestHallucinationCaught:
    def test_planted_misread_is_flagged(self):
        """The San Diego failure: density over-read must become CONFLICT + provisional."""
        for case in GOLDEN_CASES:
            wrong = case.density + 10  # plausible-but-wrong over-read
            params = NumericZoningParams(max_density_units_per_acre=wrong)
            ver = verify_numeric_params(params, [_Chunk(case.text)], case.zone_code)
            density = next(f for f in ver.fields if f.field == "max_density_units_per_acre")
            assert density.status == "conflict", f"{case.name}: misread must be flagged"
            assert ver.offer_is_provisional, f"{case.name}: misread must be provisional"
            assert str(int(case.density)) in " ".join(ver.warnings)
