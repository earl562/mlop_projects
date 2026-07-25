"""Tests for deterministic entitlement assessment + impact fees."""

from plotlot.core.types import DensityAnalysis, ZoningReport
from plotlot.pipeline.entitlement import assess_entitlement


def _report(
    state="CA",
    county="San Diego",
    zoning="RM-3-9",
    allowed=None,
    conditional=None,
    prohibited=None,
    max_units=10,
) -> ZoningReport:
    return ZoningReport(
        address="1 Main St",
        formatted_address="1 Main St",
        municipality="San Diego",
        county=county,
        state=state,
        zoning_district=zoning,
        allowed_uses=allowed or [],
        conditional_uses=conditional or [],
        prohibited_uses=prohibited or [],
        density_analysis=DensityAnalysis(
            max_units=max_units, governing_constraint="density", constraints=[]
        ),
    )


class TestPathClassification:
    def test_by_right_from_allowed_uses(self):
        a = assess_entitlement(_report(allowed=["Multifamily dwellings", "Parks"]))
        assert a.path == "by_right"
        assert a.complexity == "low"

    def test_conditional_use(self):
        a = assess_entitlement(_report(allowed=["Single-family"], conditional=["Apartment houses"]))
        assert a.path == "conditional_use"
        assert a.complexity == "medium"
        assert any("Conditional-use" in s.name for s in a.steps)

    def test_rezoning_when_prohibited(self):
        a = assess_entitlement(_report(allowed=["Retail"], prohibited=["Residential dwellings"]))
        assert a.path == "rezoning"
        assert a.complexity == "high"
        assert any("Rezoning" in s.name for s in a.steps)
        assert any("Rezoning path" in w for w in a.warnings)

    def test_inferred_by_right_from_mf_zone_code(self):
        # No use lists, but RM- code → inferred by-right.
        a = assess_entitlement(_report(zoning="RM-25", allowed=[], conditional=[]))
        assert a.path == "by_right"

    def test_unknown_when_no_signal(self):
        a = assess_entitlement(_report(zoning="C-2", allowed=[], conditional=[], prohibited=[]))
        assert a.path == "unknown"
        assert any("unknown" in w.lower() for w in a.warnings)


class TestStepsAndTimeline:
    def test_ceqa_added_for_ca_discretionary(self):
        a = assess_entitlement(_report(state="CA", conditional=["Apartments"]))
        assert any("CEQA" in s.name for s in a.steps)

    def test_no_ceqa_for_non_ca(self):
        a = assess_entitlement(_report(state="FL", county="Broward", conditional=["Apartments"]))
        assert not any("CEQA" in s.name for s in a.steps)

    def test_no_ceqa_for_by_right(self):
        a = assess_entitlement(_report(state="CA", allowed=["Multifamily"]))
        assert not any("CEQA" in s.name for s in a.steps)

    def test_timeline_is_sum_of_steps(self):
        a = assess_entitlement(_report(allowed=["Multifamily"]))
        assert a.est_timeline_months == sum(s.timeline_months for s in a.steps)
        assert a.est_timeline_months > 0


class TestImpactFees:
    def test_fees_from_regional_model(self):
        a = assess_entitlement(_report(state="CA", county="San Diego", max_units=10))
        assert a.impact_fee_per_unit == 40_000  # San Diego market
        assert a.impact_fees_total == 400_000
        assert a.fee_market == "San Diego"

    def test_fees_scale_with_units(self):
        a = assess_entitlement(_report(state="NC", county="Mecklenburg", max_units=5))
        assert a.impact_fee_per_unit == 12_000  # Charlotte metro
        assert a.impact_fees_total == 60_000

    def test_unknown_market_uses_national_default(self):
        a = assess_entitlement(_report(state="TX", county="Travis", max_units=4))
        assert a.impact_fee_per_unit == 25_000  # national default
        assert a.impact_fees_total == 100_000


class TestDeterminism:
    def test_repeatable(self):
        r = _report(conditional=["Apartments"])
        runs = [assess_entitlement(r) for _ in range(20)]
        assert all(x.path == runs[0].path for x in runs)
        assert all(x.est_timeline_months == runs[0].est_timeline_months for x in runs)
        assert all(x.impact_fees_total == runs[0].impact_fees_total for x in runs)

    def test_utilities_note_present(self):
        a = assess_entitlement(_report(allowed=["Multifamily"]))
        assert "utility" in a.utilities_note.lower() or "sewer" in a.utilities_note.lower()
