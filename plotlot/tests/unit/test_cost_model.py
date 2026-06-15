"""Tests for the regional development cost model."""

from plotlot.pipeline.cost_model import (
    NATIONAL_DEFAULT,
    get_cost_model,
)


class TestGetCostModel:
    def test_south_florida_by_county(self):
        cm = get_cost_model("FL", "Miami-Dade")
        assert cm.market == "South Florida"
        assert cm.construction_cost_psf == 225.0

    def test_bay_area(self):
        cm = get_cost_model("CA", "Santa Clara")
        assert cm.market == "SF Bay Area"
        assert cm.construction_cost_psf == 400.0
        assert cm.adv_per_unit_default == 900_000.0

    def test_san_diego_distinct_from_bay_area(self):
        sd = get_cost_model("CA", "San Diego")
        sf = get_cost_model("CA", "Alameda")
        assert sd.market == "San Diego"
        assert sd.construction_cost_psf != sf.construction_cost_psf

    def test_las_vegas(self):
        cm = get_cost_model("NV", "Clark")
        assert cm.market == "Las Vegas"

    def test_charlotte_metro(self):
        cm = get_cost_model("NC", "Mecklenburg")
        assert cm.market == "Charlotte Metro"

    def test_county_suffix_is_stripped(self):
        a = get_cost_model("CA", "San Diego County")
        b = get_cost_model("CA", "san diego")
        assert a.market == b.market == "San Diego"

    def test_unknown_county_falls_back_to_state(self):
        # FL has a state-level default even for an unmapped county.
        cm = get_cost_model("FL", "Nowhere")
        assert cm.market == "South Florida"

    def test_unknown_state_falls_back_to_national(self):
        cm = get_cost_model("TX", "Travis")
        assert cm is NATIONAL_DEFAULT
        assert cm.construction_cost_psf == 200.0

    def test_empty_inputs_return_national(self):
        assert get_cost_model("", "") is NATIONAL_DEFAULT
