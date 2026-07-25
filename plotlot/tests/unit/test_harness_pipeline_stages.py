from __future__ import annotations

from plotlot.harness.pipeline_stages import build_pipeline_stage_artifacts, build_pipeline_stages


def test_build_pipeline_stages_summarizes_live_address_path() -> None:
    stages = build_pipeline_stages(
        {
            "geocode": {
                "formatted_address": "171 NE 209th Ter, Miami, FL 33179",
            },
            "property_record": {
                "address": "171 NE 209th Ter, Miami, FL 33179",
                "folio": "30-2206-013-0310",
                "zoning_code": "R-1",
            },
            "ordinance_search": {
                "section_id": "miami-21-r1",
            },
            "comps": {
                "comparables": [{"address": "19646 NE 14 CT"}],
                "unit_comparables": [{"address": "20201 NW 15 AVE"}],
            },
            "feasibility": {
                "result": {
                    "estimated_units": 16,
                    "max_gross_buildable_sf": 13600,
                }
            },
            "noi_valuation": {
                "result": {
                    "as_built_value": 3650000,
                }
            },
            "residual_land_value": {
                "result": {
                    "max_supportable_land_price": 925000,
                }
            },
        },
        "acquisition_memo",
    )

    assert [stage.key for stage in stages] == [
        "site_identification",
        "zoning_evidence",
        "comparables",
        "feasibility",
        "underwriting",
    ]
    assert stages[0].status == "completed"
    assert stages[0].summary.endswith("(30-2206-013-0310)")
    assert stages[2].summary == "1 sales comps, 1 unit comps"
    assert stages[3].summary == "Units: 16 • Buildable sf: 13600"
    assert stages[4].summary == "As-built value: 3650000 • Max land price: 925000"


def test_build_pipeline_stages_marks_missing_underwriting_with_live_warnings() -> None:
    stages = build_pipeline_stages(
        {
            "geocode": {"formatted_address": "171 NE 209th Ter, Miami, FL 33179"},
            "property_record": {"address": "171 NE 209th Ter, Miami, FL 33179", "zoning_code": "R-1"},
            "warnings": [
                "Comparable sales search did not return qualifying comps; market pricing remains preliminary.",
                "Residual land value calculation skipped: provide cost and profit assumptions for live underwriting.",
            ],
        },
        "acquisition_memo",
    )

    assert stages[2].status == "missing"
    assert stages[3].status == "missing"
    assert stages[4].status == "warning"


def test_build_pipeline_stages_counts_pro_forma_as_underwriting_progress() -> None:
    stages = build_pipeline_stages(
        {
            "property_record": {"address": "1234 NW 15th St", "zoning_code": "RS-8"},
            "pro_forma": {
                "result": {
                    "max_supportable_land_price": 996000,
                }
            },
            "underwriting_mode": {
                "mode": "sold_unit_exit",
                "status": "partial",
                "reason": "Run relied on sold-unit exit pricing because deterministic income inputs were unavailable.",
                "source_artifacts": ["pro_forma", "cost_assumptions"],
            },
            "warnings": [
                "Income-based NOI valuation was not available; the preliminary max offer uses sold-unit pro forma math instead of rent/cap-rate income.",
            ],
        },
        "acquisition_memo",
    )

    assert stages[4].status == "completed"
    assert stages[4].summary == "As-built value: n/a • Max land price: 996000 • Basis: sold-unit exit"


def test_build_pipeline_stages_reads_top_level_live_calculator_payloads() -> None:
    stages = build_pipeline_stages(
        {
            "property_record": {"address": "1600 NW 7th Ave", "zoning_code": "CI-HD"},
            "feasibility": {
                "estimated_units": 150,
                "max_gross_buildable_sf": 348480,
            },
            "pro_forma": {
                "max_supportable_land_price": 1800000,
            },
            "underwriting_mode": {
                "mode": "sold_unit_exit",
                "status": "partial",
                "reason": "Run reached sold-unit pro forma pricing but not income-based underwriting.",
                "source_artifacts": ["pro_forma", "cost_assumptions"],
            },
        },
        "acquisition_memo",
    )

    assert stages[3].status == "completed"
    assert stages[3].summary == "Units: 150 • Buildable sf: 348480"
    assert stages[4].status == "completed"
    assert stages[4].summary == "As-built value: n/a • Max land price: 1800000 • Basis: sold-unit exit"


def test_build_pipeline_stage_artifacts_exposes_underwriting_status_for_consumers() -> None:
    stages = build_pipeline_stages(
        {
            "property_record": {"address": "1234 NW 15th St", "zoning_code": "RS-8"},
            "pro_forma": {
                "result": {
                    "max_supportable_land_price": 996000,
                }
            },
            "warnings": [
                "Income-based NOI valuation was not available; the preliminary max offer uses sold-unit pro forma math instead of rent/cap-rate income.",
            ],
        },
        "acquisition_memo",
    )

    payload = build_pipeline_stage_artifacts(stages)

    assert payload["pipeline_stage_statuses"] == {
        "site_identification": "completed",
        "zoning_evidence": "partial",
        "comparables": "missing",
        "feasibility": "missing",
        "underwriting": "partial",
    }
    assert payload["underwriting_stage"] == {
        "key": "underwriting",
        "title": "Underwriting",
        "status": "partial",
        "summary": "As-built value: n/a • Max land price: 996000",
        "artifact_keys": ["noi_valuation", "residual_land_value"],
    }
