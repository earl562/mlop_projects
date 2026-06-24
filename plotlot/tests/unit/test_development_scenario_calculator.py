from plotlot.pipeline.development_land_offer import CostStack
from plotlot.pipeline.development_scenario_calculator import (
    CommercialLeaseScenarioInputs,
    ResidentialRentalScenarioInputs,
    ResidentialSaleScenarioInputs,
    calculate_commercial_lease_scenario,
    calculate_residential_rental_scenario,
    calculate_residential_sale_scenario,
)


def test_residential_rental_scenario_is_unit_and_monthly_rent_driven() -> None:
    result = calculate_residential_rental_scenario(
        ResidentialRentalScenarioInputs(
            scenario_name="8_unit_base_rental",
            units=8,
            average_monthly_rent=2500,
            vacancy_rate_pct=5.0,
            other_income_pct_of_gsr=2.0,
            operating_expense_ratio_pct=38.0,
            market_cap_rate_pct=6.0,
            cost_stack=CostStack(
                hard_costs=900_000,
                soft_costs=180_000,
                financing_costs=50_000,
                closing_costs=20_000,
                contingency=45_000,
            ),
            market_profile_key="miami_dade_fl",
            evidence_ids=["density", "rent-comps", "cost-template"],
        )
    )

    assert result.asset_class == "residential"
    assert result.valuation_method == "rental_income_cap_rate"
    assert result.capacity_units == 8
    assert result.commercial_gla_sqft == 0
    assert result.gross_revenue == 240_000
    assert result.vacancy_loss == 12_000
    assert result.other_income == 4_800
    assert result.effective_revenue == 232_800
    assert result.operating_expenses == 88_464
    assert result.net_operating_income == 144_336
    assert result.as_built_value == 2_405_600
    assert result.land_offer.max_land_purchase_price == 609_200
    assert result.land_offer.recommended_offer == 517_820
    assert result.land_offer.max_land_purchase_price_per_unit == 76_150
    assert result.land_offer.max_land_purchase_price_per_buildable_sqft == 0
    assert result.warnings == []


def test_residential_sale_scenario_is_sellout_driven() -> None:
    result = calculate_residential_sale_scenario(
        ResidentialSaleScenarioInputs(
            scenario_name="townhome_sellout",
            units=4,
            average_sale_price_per_unit=500_000,
            selling_cost_pct_of_gross_sellout=6.0,
            required_profit_pct_of_net_sellout=20.0,
            cost_stack=CostStack(hard_costs=950_000, soft_costs=200_000, contingency=50_000),
            market_profile_key="san_diego_ca",
        )
    )

    assert result.asset_class == "residential"
    assert result.valuation_method == "for_sale_net_sellout"
    assert result.gross_revenue == 2_000_000
    assert result.selling_costs == 120_000
    assert result.effective_revenue == 1_880_000
    assert result.as_built_value == 1_880_000
    assert result.land_offer.max_land_purchase_price == 304_000
    assert result.land_offer.recommended_offer == 258_400
    assert result.land_offer.max_land_purchase_price_per_unit == 76_000


def test_commercial_lease_scenario_is_gla_and_annual_rent_psf_driven() -> None:
    result = calculate_commercial_lease_scenario(
        CommercialLeaseScenarioInputs(
            scenario_name="retail_strip_base",
            gla_sqft=12_000,
            annual_rent_psf=36,
            vacancy_rate_pct=8.0,
            operating_expense_ratio_pct=35.0,
            market_cap_rate_pct=7.0,
            cost_stack=CostStack(hard_costs=1_800_000, soft_costs=300_000, contingency=100_000),
            market_profile_key="broward_fl",
            evidence_ids=["gla", "lease-comps", "cost-template"],
        )
    )

    assert result.asset_class == "commercial"
    assert result.valuation_method == "commercial_gla_income_cap_rate"
    assert result.capacity_units == 0
    assert result.commercial_gla_sqft == 12_000
    assert result.gross_revenue == 432_000
    assert result.vacancy_loss == 34_560
    assert result.effective_revenue == 397_440
    assert result.operating_expenses == 139_104
    assert result.net_operating_income == 258_336
    assert result.as_built_value == 3_690_514.29
    assert result.land_offer.max_land_purchase_price == 567_885.71
    assert result.land_offer.recommended_offer == 482_702.86
    assert result.land_offer.max_land_purchase_price_per_unit == 0
    assert result.land_offer.max_land_purchase_price_per_buildable_sqft == 47.32
    assert result.land_offer.recommended_offer_per_buildable_sqft == 40.23
    assert result.warnings == []


def test_commercial_missing_gla_warns_without_unit_capacity_warning() -> None:
    result = calculate_commercial_lease_scenario(
        CommercialLeaseScenarioInputs(
            gla_sqft=0,
            annual_rent_psf=36,
            market_cap_rate_pct=7.0,
            cost_stack=CostStack(hard_costs=100_000),
            market_profile_key="broward_fl",
        )
    )

    joined = " ".join(result.warnings)
    assert "positive GLA" in joined
    assert "unit capacity or commercial GLA" in joined
    assert result.land_offer.max_land_purchase_price_per_buildable_sqft == 0
