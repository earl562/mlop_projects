"""Skill handler: single_parcel_feasibility — wraps run_deal_analysis.

Thin adapter that accepts a dict-based ZoningReport (serialized from
AssumptionSet.inputs_json or AnalysisRun.input_json), constructs the
domain types, delegates to the full deal analysis pipeline, and returns
the DealAnalysis serialized as a HandlerResult.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from plotlot.core.types import (
    CompAnalysis,
    DealAnalysis,
    DensityAnalysis,
    LandProForma,
    NumericZoningParams,
    PropertyRecord,
    Setbacks,
    ZoningReport,
)
from plotlot.pipeline.deal_analysis import run_deal_analysis
from plotlot.pipeline.skills.registry import HandlerResult, register_skill


def _construct_zoning_report(data: dict[str, Any]) -> ZoningReport:
    """Build a ZoningReport from a serialized dict, constructing nested dataclasses.

    Handles the gap between JSON-serialized dicts (from dataclasses.asdict())
    and the typed ZoningReport constructor. Nested dataclass fields that are
    present as dicts are reconstructed; missing or None fields are passed as
    None so that run_deal_analysis degrades gracefully.
    """
    setbacks = data.get("setbacks")
    if isinstance(setbacks, dict):
        setbacks = Setbacks(**setbacks)
    else:
        setbacks = Setbacks()

    property_record = data.get("property_record")
    if isinstance(property_record, dict):
        property_record = PropertyRecord(**property_record)

    numeric_params = data.get("numeric_params")
    if isinstance(numeric_params, dict):
        numeric_params = NumericZoningParams(**numeric_params)

    density_analysis = data.get("density_analysis")
    if isinstance(density_analysis, dict):
        density_analysis = DensityAnalysis(**density_analysis)

    comp_analysis = data.get("comp_analysis")
    if isinstance(comp_analysis, dict):
        comp_analysis = CompAnalysis(**comp_analysis)

    pro_forma = data.get("pro_forma")
    if isinstance(pro_forma, dict):
        pro_forma = LandProForma(**pro_forma)

    deal_analysis = data.get("deal_analysis")
    if isinstance(deal_analysis, dict):
        deal_analysis = DealAnalysis(**deal_analysis)

    return ZoningReport(
        address=data.get("address", ""),
        formatted_address=data.get("formatted_address", ""),
        municipality=data.get("municipality", ""),
        county=data.get("county", ""),
        lat=data.get("lat"),
        lng=data.get("lng"),
        zoning_district=data.get("zoning_district", ""),
        zoning_description=data.get("zoning_description", ""),
        allowed_uses=data.get("allowed_uses", []),
        conditional_uses=data.get("conditional_uses", []),
        prohibited_uses=data.get("prohibited_uses", []),
        setbacks=setbacks,
        max_height=data.get("max_height", ""),
        max_density=data.get("max_density", ""),
        floor_area_ratio=data.get("floor_area_ratio", ""),
        lot_coverage=data.get("lot_coverage", ""),
        min_lot_size=data.get("min_lot_size", ""),
        parking_requirements=data.get("parking_requirements", ""),
        property_record=property_record,
        numeric_params=numeric_params,
        density_analysis=density_analysis,
        comp_analysis=comp_analysis,
        pro_forma=pro_forma,
        deal_analysis=deal_analysis,
        summary=data.get("summary", ""),
        sources=data.get("sources", []),
        confidence=data.get("confidence", ""),
        source_refs=data.get("source_refs", []),
        validation_warnings=data.get("validation_warnings", []),
        site_risk=data.get("site_risk"),
        lookup_snapshot=data.get("lookup_snapshot"),
    )


@register_skill("single_parcel_feasibility")
async def handle_single_parcel_feasibility(inputs_json: dict[str, Any]) -> HandlerResult:
    """Run the full deal analysis pipeline for a single parcel.

    Args:
        inputs_json: Dictionary containing:
            - zoning_report: Serialized ZoningReport dict
            - county: County name (e.g. "miami_dade")
            - state: Two-letter state code (e.g. "FL")
            - land_purchase_price: Asking/contract price for the land ($)
            - zip_code: Optional ZIP code
            - evidence_ids: Optional list of evidence IDs

    Returns:
        HandlerResult with the DealAnalysis serialized as output_json.
    """
    zoning_report = _construct_zoning_report(inputs_json["zoning_report"])
    county: str = inputs_json["county"]
    state: str = inputs_json["state"]
    land_purchase_price: float = inputs_json["land_purchase_price"]
    zip_code: str = inputs_json.get("zip_code", "")

    result: DealAnalysis = await run_deal_analysis(
        zoning_report=zoning_report,
        county=county,
        state=state,
        land_purchase_price=land_purchase_price,
        zip_code=zip_code,
    )

    return HandlerResult(
        output_json=dataclasses.asdict(result),
        evidence_ids=inputs_json.get("evidence_ids", []),
    )
