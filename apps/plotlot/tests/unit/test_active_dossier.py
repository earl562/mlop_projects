"""Active Property Dossier contract tests."""

from plotlot.core.types import (
    ConstraintResult,
    DensityAnalysis,
    NumericZoningParams,
    PropertyRecord,
    Setbacks,
    SourceRef,
    ZoningReport,
)
from plotlot.pipeline.dossier import build_active_property_dossier


def _report() -> ZoningReport:
    return ZoningReport(
        address="171 NE 209th Ter, Miami, FL 33179",
        formatted_address="171 NE 209th Ter, Miami Gardens, FL 33179",
        municipality="Miami Gardens",
        county="Miami-Dade",
        lat=25.957,
        lng=-80.199,
        zoning_district="R-1",
        zoning_description="Single-Family Residential",
        setbacks=Setbacks(front="25 ft", side="7.5 ft", rear="25 ft"),
        max_height="35 ft / 2 stories",
        max_density="6 units per acre",
        floor_area_ratio="0.50",
        lot_coverage="40%",
        min_lot_size="7,500 sq ft",
        parking_requirements="2 spaces per dwelling unit",
        property_record=PropertyRecord(
            folio="3422120000010",
            address="171 NE 209TH TER",
            municipality="Miami Gardens",
            county="Miami-Dade",
            zoning_code="R-1",
            lot_size_sqft=7500.0,
            lot_dimensions="75 x 100",
        ),
        numeric_params=NumericZoningParams(min_lot_width_ft=75.0),
        density_analysis=DensityAnalysis(
            max_units=1,
            governing_constraint="density",
            constraints=[
                ConstraintResult(
                    name="density",
                    max_units=1,
                    raw_value=1.033,
                    formula="7500 sqft * 6.0 units/acre / 43560 = 1.033",
                    is_governing=True,
                )
            ],
            lot_size_sqft=7500.0,
            lot_width_ft=75.0,
            lot_depth_ft=100.0,
            confidence="high",
        ),
        sources=["Sec. 34-342 — R-1 Single-Family Residential"],
        source_refs=[
            SourceRef(
                section="Sec. 34-342",
                section_title="R-1 Single-Family Residential",
                chunk_text_preview="The R-1 district permits single-family residential uses.",
                score=0.92,
            )
        ],
        confidence="high",
    )


def test_active_property_dossier_projects_report_truth():
    dossier = build_active_property_dossier(
        _report(),
        freshness_timestamp="2026-05-13T00:00:00+00:00",
    )

    assert dossier["resolved_address"] == "171 NE 209th Ter, Miami Gardens, FL 33179"
    assert dossier["parcel_id"] == "3422120000010"
    assert dossier["municipality"] == "Miami Gardens"
    assert dossier["county"] == "Miami-Dade"
    assert dossier["state"] == "FL"
    assert dossier["zoning_district"] == "R-1"
    assert dossier["lot_facts"] == {
        "lot_size_sqft": 7500.0,
        "lot_dimensions": "75 x 100",
        "lot_width_ft": 75.0,
        "lot_depth_ft": 100.0,
    }
    assert dossier["dimensional_standards"]["setbacks"] == {
        "front": "25 ft",
        "side": "7.5 ft",
        "rear": "25 ft",
    }
    assert dossier["max_units"] == 1
    assert dossier["governing_constraint"] == "density"
    assert dossier["confidence"] == "high"
    assert dossier["freshness_timestamp"] == "2026-05-13T00:00:00+00:00"
    assert dossier["evidence_refs"][0]["kind"] == "ordinance_section"
    assert dossier["evidence_refs"][0]["source"] == "Sec. 34-342"
    assert dossier["evidence_refs"][-1]["kind"] == "property_record"
