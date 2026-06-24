from plotlot.pipeline.development_land_offer import (
    AsBuiltValueInputs,
    CostStack,
    DevelopmentLandOfferInputs,
    calculate_as_built_value,
    calculate_development_land_offer,
)


def test_calculate_as_built_value_from_noi_and_cap_rate() -> None:
    assert calculate_as_built_value(annual_noi=120_000, market_cap_rate_pct=6.0) == 2_000_000


def test_calculate_development_land_offer_income_approach_base_case() -> None:
    result = calculate_development_land_offer(
        DevelopmentLandOfferInputs(
            scenario_name="base",
            max_units=8,
            as_built_value=AsBuiltValueInputs(
                annual_noi=180_000,
                market_cap_rate_pct=6.0,
            ),
            cost_stack=CostStack(
                hard_costs=1_400_000,
                soft_costs=280_000,
                financing_costs=90_000,
                closing_costs=25_000,
                contingency=70_000,
            ),
            desired_sweat_equity_pct=25.0,
            recommended_offer_pct_of_max=85.0,
            evidence_ids=["density-run-1", "rent-comps-1", "cost-template-1"],
            assumption_ids=["base-rent", "base-cap-rate"],
        )
    )

    assert result.as_built_value == 3_000_000
    assert result.total_costs_before_land == 1_865_000
    assert result.desired_sweat_equity == 750_000
    assert result.max_land_purchase_price == 385_000
    assert result.recommended_offer == 327_250
    assert result.max_land_purchase_price_per_unit == 48_125
    assert result.recommended_offer_per_unit == 40_906.25
    assert result.as_built_value_source == "income_approach"
    assert result.confidence == "high"
    assert result.warnings == []


def test_calculate_development_land_offer_uses_override_value() -> None:
    result = calculate_development_land_offer(
        DevelopmentLandOfferInputs(
            max_units=4,
            as_built_value=AsBuiltValueInputs(
                annual_noi=0,
                market_cap_rate_pct=0,
                override_value=1_200_000,
                value_source="sales_comp_override",
            ),
            cost_stack=CostStack(hard_costs=650_000, soft_costs=130_000),
            desired_sweat_equity_pct=20.0,
            recommended_offer_pct_of_max=90.0,
        )
    )

    assert result.as_built_value == 1_200_000
    assert result.as_built_value_source == "sales_comp_override"
    assert result.max_land_purchase_price == 180_000
    assert result.recommended_offer == 162_000


def test_negative_residual_land_value_is_preserved_but_offer_is_zero() -> None:
    result = calculate_development_land_offer(
        DevelopmentLandOfferInputs(
            max_units=6,
            as_built_value=AsBuiltValueInputs(override_value=1_000_000),
            cost_stack=CostStack(hard_costs=900_000, soft_costs=250_000, contingency=100_000),
            desired_sweat_equity_pct=25.0,
        )
    )

    assert result.max_land_purchase_price == -500_000
    assert result.recommended_offer == 0
    assert "Residual land value is negative" in " ".join(result.warnings)
    assert result.confidence == "low"


def test_missing_value_inputs_return_low_confidence_with_warnings() -> None:
    result = calculate_development_land_offer(
        DevelopmentLandOfferInputs(
            max_units=0,
            as_built_value=AsBuiltValueInputs(),
            cost_stack=CostStack(),
        )
    )

    assert result.as_built_value == 0
    assert result.max_land_purchase_price == 0
    assert result.recommended_offer == 0
    assert result.confidence == "low"
    assert any("No positive unit capacity" in warning for warning in result.warnings)
    assert any("No development costs" in warning for warning in result.warnings)
    assert any("Annual NOI" in warning for warning in result.warnings)


def test_out_of_range_percentages_fall_back_to_defaults() -> None:
    result = calculate_development_land_offer(
        DevelopmentLandOfferInputs(
            max_units=2,
            as_built_value=AsBuiltValueInputs(override_value=500_000),
            cost_stack=CostStack(hard_costs=200_000),
            desired_sweat_equity_pct=125.0,
            recommended_offer_pct_of_max=-10.0,
        )
    )

    # Defaults: 25% desired equity and 85% offer factor.
    assert result.max_land_purchase_price == 175_000
    assert result.recommended_offer == 148_750
    assert any("desired_sweat_equity_pct" in warning for warning in result.warnings)
    assert any("recommended_offer_pct_of_max" in warning for warning in result.warnings)
