from __future__ import annotations

from plotlot.harness.evaluation_readiness import assess_live_evaluation_readiness


def test_acquisition_evaluation_is_blocked_when_ordinance_capacity_is_missing() -> None:
    readiness = assess_live_evaluation_readiness(
        analysis_type="acquisition_memo",
        artifacts={
            "property_record": {
                "folio": "74434321060170150",
                "lot_size_sqft": 7000,
                "zoning_code": "NWD-R",
            },
            "comps": {
                "estimated_land_value_low": 282805.0,
                "estimated_land_value_high": 653589.0,
            },
            "underwriting_mode": {
                "mode": "missing_income_inputs",
                "status": "warning",
            },
        },
    )

    assert readiness.status == "blocked"
    assert readiness.can_recommend is False
    assert "official_dimensional_standards" in readiness.missing_requirements
    assert "deterministic_feasibility" in readiness.missing_requirements
    assert "verified_underwriting_inputs" in readiness.missing_requirements
    assert "valuation" not in readiness.allowed_outputs


def test_acquisition_evaluation_rejects_authority_metadata_without_dimensional_rules() -> None:
    readiness = assess_live_evaluation_readiness(
        analysis_type="acquisition_memo",
        artifacts={
            "property_record": {
                "folio": "74434321060170150",
                "lot_size_sqft": 7000,
                "zoning_code": "NWD-R",
            },
            "ordinance_rules": {
                "authority_is_live": True,
                "authority_is_official": True,
                "requires_official_verification": False,
                "source_url": "https://example.gov/code",
                "source_section_id": "Sec. 94-000",
            },
            "feasibility": {"estimated_units": 4},
            "comping_workflow": {
                "trust_gates": {"underwriting_status": "available_to_underwriting"}
            },
            "underwriting_mode": {"status": "completed"},
            "cost_assumptions": {
                "requires_official_verification": False,
                "construction_cost_psf": 225,
            },
        },
    )

    assert readiness.status == "blocked"
    assert "official_dimensional_standards" in readiness.missing_requirements


def test_acquisition_evaluation_rejects_completed_but_unverified_underwriting() -> None:
    readiness = assess_live_evaluation_readiness(
        analysis_type="acquisition_memo",
        artifacts={
            "property_record": {
                "folio": "74434321060170150",
                "lot_size_sqft": 7000,
                "zoning_code": "NWD-R",
            },
            "ordinance_rules": {
                "authority_is_live": True,
                "authority_is_official": True,
                "requires_official_verification": False,
                "source_url": "https://example.gov/code",
                "source_section_id": "Sec. 94-121",
                "max_density_units_per_acre": 12,
            },
            "feasibility": {"estimated_units": 2},
            "comping_workflow": {
                "trust_gates": {"underwriting_status": "available_to_underwriting"}
            },
            "underwriting_mode": {
                "mode": "income_cap_rate",
                "status": "completed",
            },
            "cost_assumptions": {
                "requires_official_verification": True,
                "construction_cost_psf": 225,
                "monthly_rent_per_unit": 2800,
                "vacancy_pct": 5,
                "operating_expense_pct": 35,
                "cap_rate": 5.5,
            },
        },
    )

    assert readiness.status == "blocked"
    assert "verified_underwriting_inputs" in readiness.missing_requirements


def test_acquisition_evaluation_rejects_zero_value_driving_inputs() -> None:
    readiness = assess_live_evaluation_readiness(
        analysis_type="acquisition_memo",
        artifacts={
            "property_record": {
                "folio": "74434321060170150",
                "lot_size_sqft": 7000,
                "zoning_code": "NWD-R",
            },
            "ordinance_rules": {
                "authority_is_live": True,
                "authority_is_official": True,
                "requires_official_verification": False,
                "source_url": "https://example.gov/code",
                "source_section_id": "Sec. 94-121",
                "max_density_units_per_acre": 12,
            },
            "feasibility": {"estimated_units": 2},
            "comping_workflow": {
                "trust_gates": {"underwriting_status": "available_to_underwriting"}
            },
            "underwriting_mode": {
                "mode": "income_cap_rate",
                "status": "completed",
            },
            "cost_assumptions": {
                "requires_official_verification": False,
                "construction_cost_psf": 0,
                "monthly_rent_per_unit": 0,
                "vacancy_pct": 0,
                "operating_expense_pct": 35,
                "cap_rate": 0,
            },
        },
    )

    assert readiness.status == "blocked"
    assert "verified_underwriting_inputs" in readiness.missing_requirements


def test_sold_exit_evaluation_ignores_unverified_income_defaults() -> None:
    readiness = assess_live_evaluation_readiness(
        analysis_type="acquisition_memo",
        artifacts={
            "property_record": {
                "folio": "30-5009-025-0010",
                "lot_size_sqft": 77842,
                "zoning_code": "EU-1",
            },
            "ordinance_rules": {
                "authority_is_live": True,
                "authority_is_official": True,
                "requires_official_verification": False,
                "source_url": "https://library.municode.com/example/code",
                "source_section_id": "Sec. 33-196",
                "far": 0.4,
                "max_density_units_per_acre": 2.5,
            },
            "feasibility": {"estimated_units": 4},
            "comping_workflow": {
                "trust_gates": {"underwriting_status": "available_to_underwriting"}
            },
            "underwriting_mode": {
                "mode": "sold_unit_exit",
                "status": "completed",
            },
            "cost_assumptions": {
                "requires_official_verification": False,
                "requires_income_assumption_verification": True,
                "construction_cost_psf": 225,
                "avg_unit_size_sqft": 1800,
                "soft_cost_pct": 20,
                "builder_margin_pct": 15,
                "impact_fees_per_unit": 25000,
            },
        },
    )

    assert readiness.status == "ready"
    assert readiness.can_recommend is True
    assert readiness.missing_requirements == []
    assert "valuation" in readiness.allowed_outputs
