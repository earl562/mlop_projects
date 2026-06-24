from plotlot.pipeline.development_market_profile import (
    estimate_commercial_cost_stack,
    estimate_residential_cost_stack,
    get_development_market_profile,
    normalize_market_key,
)


def test_normalize_market_key_removes_county_suffix() -> None:
    assert normalize_market_key("Miami-Dade County", "FL") == "miami_dade_fl"


def test_get_development_market_profile_prefers_city_specific_profile() -> None:
    profile = get_development_market_profile(
        state="CA",
        county="San Diego",
        municipality="San Diego",
    )

    assert profile.key == "san_diego_ca"
    assert profile.entitlement_risk == "high"


def test_get_development_market_profile_uses_county_alias() -> None:
    profile = get_development_market_profile(state="CA", county="Alameda")

    assert profile.key == "bay_area_ca"


def test_get_development_market_profile_falls_back_to_national_default() -> None:
    profile = get_development_market_profile(state="ZZ", county="Unknown")

    assert profile.key == "national_default"


def test_estimate_residential_cost_stack_uses_units_and_local_costs() -> None:
    profile = get_development_market_profile(
        state="CA",
        county="San Diego",
        municipality="San Diego",
    )

    estimate = estimate_residential_cost_stack(
        profile=profile,
        units=4,
        average_unit_size_sqft=1000,
        as_built_value=2_000_000,
    )

    assert estimate.market_profile_key == "san_diego_ca"
    assert estimate.gross_building_area_sqft == 4_000
    assert estimate.cost_basis == "residential_units_x_average_unit_size"
    assert estimate.cost_stack.hard_costs == 1_280_000
    assert estimate.cost_stack.impact_fees == 140_000
    assert estimate.cost_stack.risk_buffer == 100_000
    assert estimate.cost_stack.total_excluding_land == 2_129_280
    assert any("asset_class=residential" in note for note in estimate.assumption_notes)


def test_estimate_commercial_cost_stack_uses_gla_not_units() -> None:
    profile = get_development_market_profile(state="FL", county="Miami-Dade")

    estimate = estimate_commercial_cost_stack(
        profile=profile,
        gla_sqft=10_000,
        as_built_value=3_000_000,
    )

    assert estimate.market_profile_key == "miami_dade_fl"
    assert estimate.gross_building_area_sqft == 10_000
    assert estimate.cost_basis == "commercial_gla_sqft"
    assert estimate.cost_stack.hard_costs == 2_450_000
    assert estimate.cost_stack.impact_fees == 45_000
    assert estimate.cost_stack.risk_buffer == 90_000
    assert estimate.cost_stack.total_excluding_land == 3_499_340
    assert any("Commercial costs" in note for note in estimate.assumption_notes)
