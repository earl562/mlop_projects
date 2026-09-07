"""Tests for the Deal Paper one-page investment memo generator."""

from plotlot.documents.deal_paper import (
    _fmt_money,
    _fmt_range,
    _verdict,
    generate_deal_paper_pdf,
)


def _full_report() -> dict:
    return {
        "address": "1233 Hueneme St, San Diego, CA 92110",
        "formatted_address": "1233 Hueneme St, San Diego, CA 92110",
        "municipality": "San Diego",
        "county": "San Diego",
        "zoning_district": "RM-3-7",
        "zoning_description": "Multifamily residential",
        "summary": "Strong infill multifamily site with positive residual.",
        "confidence": "high",
        "property_record": {"lot_size_sqft": 10000, "owner": "Doe Family Trust"},
        "density_analysis": {
            "max_units": 8,
            "governing_constraint": "density",
            "confidence": "high",
        },
        "comp_analysis": {
            "median_price_per_acre": 2_000_000,
            "price_per_acre_low": 1_700_000,
            "price_per_acre_high": 2_300_000,
            "estimated_land_value": 459_000,
            "estimated_land_value_low": 390_000,
            "estimated_land_value_high": 528_000,
            "adv_per_unit": 760_000,
            "adv_per_unit_low": 710_000,
            "adv_per_unit_high": 820_000,
            "adv_source": "comps",
            "confidence": 0.9,
            "comparables": [{"address": "x"}, {"address": "y"}],
            "unit_comparables": [{"address": "z"}],
        },
        "pro_forma": {
            "gross_development_value": 6_080_000,
            "hard_costs": 2_940_000,
            "soft_costs": 646_800,
            "builder_margin": 1_520_000,
            "max_land_price": 973_200,
            "cost_per_door": 448_350,
            "construction_cost_psf": 350,
            "soft_cost_pct": 22,
            "builder_margin_pct": 25,
            "avg_unit_size_sqft": 1050,
            "adv_per_unit": 760_000,
            "adv_source": "comps",
            "market": "San Diego",
            "max_units": 8,
        },
        "site_risk": {
            "flood_zone": {"zone": "X", "risk_level": "minimal"},
            "has_wetlands": False,
            "overall_risk": "low",
            "risk_flags": [],
        },
    }


class TestGenerateDealPaper:
    def test_full_report_produces_pdf(self):
        pdf = generate_deal_paper_pdf(_full_report())
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1500

    def test_empty_report_does_not_crash(self):
        pdf = generate_deal_paper_pdf({})
        assert pdf.startswith(b"%PDF")

    def test_warnings_callout_renders(self):
        report = _full_report()
        report["warnings"] = [
            "Implied density is 311 units/acre — unusually high. Verify the zoning density.",
            "ADV per unit is a regional market estimate — confirm exit pricing.",
        ]
        pdf = generate_deal_paper_pdf(report)
        assert pdf.startswith(b"%PDF")

    def test_density_upside_section_renders(self):
        report = _full_report()
        report["density_uplift"] = {
            "base_units": 8,
            "state": "CA",
            "max_potential_units": 12,
            "programs": [
                {
                    "name": "ADU (detached)",
                    "statute": "CA Gov. Code §66310 et seq.",
                    "potential_units": 10,
                    "requirements": "Ministerial.",
                },
                {
                    "name": "Density Bonus",
                    "statute": "CA Gov. Code §65915",
                    "potential_units": 12,
                    "requirements": "15% very-low-income set-aside.",
                },
            ],
            "notes": [],
        }
        pdf = generate_deal_paper_pdf(report)
        assert pdf.startswith(b"%PDF")

    def test_explicit_sensitivity_renders(self):
        report = _full_report()
        report["sensitivity"] = {
            "row_label": "Construction $/sf",
            "col_label": "ADV per Unit",
            "row_values": [280, 315, 350, 385, 420],
            "col_values": [608_000, 684_000, 760_000, 836_000, 912_000],
            "grid": [
                [1_200_000, 1_500_000, 1_800_000, 2_100_000, 2_400_000],
                [900_000, 1_200_000, 1_500_000, 1_800_000, 2_100_000],
                [600_000, 900_000, 1_200_000, 1_500_000, 1_800_000],
                [300_000, 600_000, 900_000, 1_200_000, 1_500_000],
                [-100_000, 200_000, 500_000, 800_000, 1_100_000],
            ],
            "base_row_index": 2,
            "base_col_index": 2,
            "base_value": 1_200_000,
            "notes": [],
        }
        pdf = generate_deal_paper_pdf(report)
        assert pdf.startswith(b"%PDF")

    def test_nested_none_sections_handled(self):
        report = {
            "address": "1 Test St",
            "comp_analysis": None,
            "pro_forma": None,
            "site_risk": None,
            "density_analysis": None,
            "property_record": None,
        }
        pdf = generate_deal_paper_pdf(report)
        assert pdf.startswith(b"%PDF")


class TestFormatHelpers:
    def test_fmt_money(self):
        assert _fmt_money(1_234_567) == "$1,234,567"
        assert _fmt_money(0) == "—"
        assert _fmt_money(None) == "—"
        assert _fmt_money("nan-ish") == "—"

    def test_fmt_range(self):
        assert _fmt_range(100_000, 200_000) == "$100,000 – $200,000"
        assert _fmt_range(0, 0) == "—"
        assert _fmt_range(150_000, 150_000) == "$150,000"


class TestVerdict:
    def test_negative_residual_flags_red(self):
        text, _ = _verdict(0, 0.9)
        assert "Negative" in text or "revisit" in text

    def test_strong_confidence_proceed(self):
        text, _ = _verdict(500_000, 0.9)
        assert "diligence" in text

    def test_thin_confidence_caution(self):
        text, _ = _verdict(500_000, 0.4)
        assert "confidence" in text
