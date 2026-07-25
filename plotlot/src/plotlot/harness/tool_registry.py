"""Typed tool contracts for the agent harness.

The same tool contracts should be shared across REST adapters, chat, and MCP.
"""

from __future__ import annotations

from typing import Any

from plotlot.harness.full_harness_chat_contracts import full_harness_chat_tool_contracts
from plotlot.land_use.models import ToolContract, ToolRiskClass


_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "geocode_address": ToolContract(
        name="geocode_address",
        description="Resolve an address to municipality/county/state and coordinates.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {"address": {"type": "string", "minLength": 3}},
            "required": ["address"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "object"},
                "evidence": {"type": "array"},
            },
            "required": ["status", "result"],
        },
    ),
    "lookup_property_info": ToolContract(
        name="lookup_property_info",
        description="Lookup parcel/property facts from county records/GIS.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "minLength": 3},
                "county": {"type": "string", "minLength": 3},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
            },
            "required": ["address", "county", "lat", "lng"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "object"},
                "evidence": {"type": "array"},
            },
            "required": ["status", "result"],
        },
    ),
    "search_zoning_ordinance": ToolContract(
        name="search_zoning_ordinance",
        description="Search local ordinance/chunk index for relevant sections.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "municipality": {"type": "string", "minLength": 2},
                "query": {"type": "string", "minLength": 1},
            },
            "required": ["municipality", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
            },
        },
    ),
    "search_south_florida_gis": ToolContract(
        name="search_south_florida_gis",
        description="Search the shared South Florida GIS source catalog.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "county": {"type": "string"},
            },
            "required": ["query"],
        },
        output_schema={"type": "object", "properties": {"results": {"type": "array"}}},
    ),
    "get_gis_source_metadata": ToolContract(
        name="get_gis_source_metadata",
        description="Load one South Florida GIS source catalog entry by source ID.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {"source_id": {"type": "string", "minLength": 1}},
            "required": ["source_id"],
        },
        output_schema={"type": "object", "properties": {"source": {"type": "object"}}, "required": ["source"]},
    ),
    "query_gis_feature_service": ToolContract(
        name="query_gis_feature_service",
        description="Query a South Florida GIS feature-service source through the shared lane.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "minLength": 1},
                "where": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["source_id", "where"],
        },
        output_schema={"type": "object"},
    ),
    "classify_gis_applicability": ToolContract(
        name="classify_gis_applicability",
        description="Classify whether a GIS source is direct or contextual for a site.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "minLength": 1},
                "county": {"type": "string", "minLength": 1},
                "municipality": {"type": "string"},
                "is_unincorporated_or_bmsd": {"type": "boolean"},
            },
            "required": ["source_id", "county"],
        },
        output_schema={"type": "object"},
    ),
    "resolve_site_boundary_context": ToolContract(
        name="resolve_site_boundary_context",
        description="Resolve shared county/municipality/BMSD site-boundary context for South Florida GIS use.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 1},
                "municipality": {"type": "string"},
            },
            "required": ["county"],
        },
        output_schema={"type": "object"},
    ),
    "capture_public_listing_comps": ToolContract(
        name="capture_public_listing_comps",
        description=(
            "Capture public sold-listing candidates from browser automation for off-market comping. "
            "Candidates remain contextual until county-reconciled."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "minLength": 3},
                "county": {"type": "string", "minLength": 1},
                "municipality": {"type": "string"},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "lot_size_sqft": {"type": "number", "minimum": 0},
                "zoning_code": {"type": "string"},
            },
            "required": ["address", "county"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "provider": {"type": "string"},
                "strategy": {"type": "string"},
                "candidates": {"type": "array"},
                "warnings": {"type": "array"},
            },
            "required": ["status", "provider", "strategy", "candidates"],
        },
    ),
    "run_deal_analysis": ToolContract(
        name="run_deal_analysis",
        description="Run the shared PlotLot harness analysis flow for one address.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "minLength": 3},
                "analysis_type": {"type": "string"},
                "analysisType": {"type": "string"},
                "assumptions": {"type": "object"},
            },
            "required": ["address"],
        },
        output_schema={"type": "object"},
    ),
    "analyze_property": ToolContract(
        name="analyze_property",
        description=(
            "Full deterministic deal analysis for one address — verified buildable "
            "units, comps, residual offer, impact fees, site/coastal risk, entitlement "
            "path, and CA density upside. The grounded engine the agent must cite."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {"address": {"type": "string", "minLength": 3}},
            "required": ["address"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "by_right": {"type": "object"},
                "valuation": {"type": "object"},
            },
            "required": ["status"],
        },
    ),
    "calculate": ToolContract(
        name="calculate",
        description=(
            "Deterministic arithmetic evaluator. The agent calls this for ALL math so "
            "no number is computed by LLM mental arithmetic. Pure arithmetic only — no "
            "code-exec surface."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {"expression": {"type": "string", "minLength": 1}},
            "required": ["expression"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "number"},
                "expression": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
    "analyze_upzoning": ToolContract(
        name="analyze_upzoning",
        description=(
            "Deterministic entitlement value-creation calculator. Compares a by-right "
            "baseline yield to an upzoned/subdivided target and computes the instant "
            "equity created before building. Per-lot value is a caller input, never "
            "fabricated."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {"lot_sqft": {"type": "number"}},
            "required": ["lot_sqft"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "equity_created": {"type": "number"},
                "upzoned": {"type": "object"},
            },
            "required": ["status"],
        },
    ),
    "screen_properties": ToolContract(
        name="screen_properties",
        description=(
            "Batch buy-box screening across many addresses; returns qualified deals "
            "ranked by the deterministic residual max land offer."
        ),
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "addresses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "states": {"type": "array", "items": {"type": "string"}},
                "counties": {"type": "array", "items": {"type": "string"}},
                "zoning_prefixes": {"type": "array", "items": {"type": "string"}},
                "min_lot_sqft": {"type": "number"},
                "max_lot_sqft": {"type": "number"},
                "min_units": {"type": "integer"},
                "min_residual": {"type": "number"},
                "require_verified": {"type": "boolean"},
                "exclude_high_flood_risk": {"type": "boolean"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["addresses"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "qualified": {"type": "array"},
                "qualified_count": {"type": "integer"},
            },
            "required": ["status"],
        },
        budget_cents=50,
    ),
    "compute_feasibility": ToolContract(
        name="compute_feasibility",
        description="Run the shared harness feasibility calculator.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "lot_area_sf": {"type": "number"},
                "max_far": {"type": "number"},
                "max_units": {"type": "integer"},
                "lot_frontage_ft": {"type": "number"},
                "lot_depth_ft": {"type": "number"},
                "setback_front_ft": {"type": "number"},
                "setback_side_ft": {"type": "number"},
                "setback_rear_ft": {"type": "number"},
                "max_lot_coverage_pct": {"type": "number"},
                "efficiency_factor": {"type": "number"},
                "avg_unit_size_sf": {"type": "number"},
                "parking_spaces_per_unit": {"type": "number"},
            },
            "required": ["lot_area_sf", "efficiency_factor", "avg_unit_size_sf"],
        },
        output_schema={"type": "object"},
    ),
    "find_comparables": ToolContract(
        name="find_comparables",
        description=(
            "Run the shared harness comparable-sales lane to produce cited land comps, "
            "exit comps, land value range, and ADV-per-unit."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 1},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "address": {"type": "string"},
                "state": {"type": "string", "minLength": 2},
                "municipality": {"type": "string"},
                "zoning_code": {"type": "string"},
                "land_use_code": {"type": "string"},
                "land_use_description": {"type": "string"},
                "lot_size_sqft": {"type": "number", "minimum": 0},
                "living_units": {"type": "integer", "minimum": 0},
                "radius_miles": {"type": "number", "exclusiveMinimum": 0},
                "months": {"type": "integer", "minimum": 1},
                "max_comps": {"type": "integer", "minimum": 1},
            },
            "required": ["county", "lat", "lng"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "subject": {"type": "object"},
                "analysis": {"type": "object"},
                "evidence": {"type": "array"},
            },
            "required": ["subject", "analysis"],
        },
    ),
    "load_rental_market_evidence": ToolContract(
        name="load_rental_market_evidence",
        description=(
            "Resolve shared rental market evidence for underwriting assumptions, "
            "including rent, vacancy, opex, and cap-rate defaults or overrides."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "state": {"type": "string", "minLength": 2},
                "county": {"type": "string"},
                "municipality": {"type": "string"},
                "assumptions": {"type": "object"},
            },
            "required": ["state"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "rental_market_evidence": {"type": "object"},
                "evidence": {"type": "array"},
            },
            "required": ["rental_market_evidence"],
        },
    ),
    "load_underwriting_market_profile": ToolContract(
        name="load_underwriting_market_profile",
        description=(
            "Resolve the shared regional underwriting market profile, including cost "
            "assumptions and any inferred rent, vacancy, opex, or cap-rate defaults."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "state": {"type": "string", "minLength": 2},
                "county": {"type": "string"},
                "municipality": {"type": "string"},
                "assumptions": {"type": "object"},
            },
            "required": ["state"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "profile": {"type": "object"},
                "evidence": {"type": "array"},
            },
            "required": ["profile"],
        },
    ),
    "run_noi_valuation": ToolContract(
        name="run_noi_valuation",
        description="Run the shared harness NOI/as-built value calculator.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "unit_count": {"type": "integer"},
                "monthly_rent_per_unit": {"type": "number"},
                "vacancy_pct": {"type": "number"},
                "operating_expense_pct": {"type": "number"},
                "cap_rate": {"type": "number"},
            },
            "required": [
                "unit_count",
                "monthly_rent_per_unit",
                "vacancy_pct",
                "operating_expense_pct",
                "cap_rate",
            ],
        },
        output_schema={"type": "object"},
    ),
    "run_pro_forma": ToolContract(
        name="run_pro_forma",
        description="Run the shared harness land pro forma calculator for max offer math.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "state": {"type": "string", "minLength": 2},
                "county": {"type": "string"},
                "max_units": {"type": "integer", "minimum": 1},
                "adv_per_unit": {"type": "number", "minimum": 0},
                "estimated_land_value": {"type": "number", "minimum": 0},
                "construction_cost_psf": {"type": "number", "exclusiveMinimum": 0},
                "avg_unit_size_sqft": {"type": "number", "exclusiveMinimum": 0},
                "soft_cost_pct": {"type": "number", "minimum": 0},
                "builder_margin_pct": {"type": "number", "minimum": 0},
                "impact_fees_per_unit": {"type": "number", "minimum": 0},
            },
            "required": ["state", "max_units"],
        },
        output_schema={"type": "object"},
    ),
    "run_residual_land_value": ToolContract(
        name="run_residual_land_value",
        description="Run the shared harness residual land value calculator.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "as_built_value": {"type": "number"},
                "desired_profit": {"type": "number"},
                "hard_costs": {"type": "number"},
                "soft_costs": {"type": "number"},
                "contingency": {"type": "number"},
                "developer_fee": {"type": "number"},
                "closing_costs": {"type": "number"},
                "financing_costs": {"type": "number"},
                "holding_costs": {"type": "number"},
                "selling_costs": {"type": "number"},
                "asking_price": {"type": "number"},
            },
            "required": [
                "as_built_value",
                "desired_profit",
                "hard_costs",
                "soft_costs",
                "contingency",
                "developer_fee",
                "closing_costs",
                "financing_costs",
                "holding_costs",
                "selling_costs",
            ],
        },
        output_schema={"type": "object"},
    ),
    "run_brrrr_refinance_analysis": ToolContract(
        name="run_brrrr_refinance_analysis",
        description="Run the shared harness BRRRR/refinance calculator.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "total_project_cost": {"type": "number"},
                "stabilized_value": {"type": "number"},
                "refinance_ltv": {"type": "number"},
                "annual_interest_rate": {"type": "number"},
                "amortization_years": {"type": "integer"},
                "annual_noi": {"type": "number"},
                "cash_in_deal": {"type": "number"},
            },
            "required": [
                "total_project_cost",
                "stabilized_value",
                "refinance_ltv",
                "annual_interest_rate",
                "amortization_years",
                "annual_noi",
                "cash_in_deal",
            ],
        },
        output_schema={"type": "object"},
    ),
    "run_sensitivity_analysis": ToolContract(
        name="run_sensitivity_analysis",
        description="Run the shared harness residual land value sensitivity calculator.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "base": {"type": "object"},
                "value_adjustments_pct": {"type": "array", "items": {"type": "number"}},
                "cost_adjustments_pct": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["base"],
        },
        output_schema={"type": "object"},
    ),
    "create_construction_budget": ToolContract(
        name="create_construction_budget",
        description="Run the shared harness construction budget calculator.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "line_items": {"type": "array", "items": {"type": "object"}},
                "contingency_pct": {"type": "number"},
                "developer_fee_pct": {"type": "number"},
            },
            "required": ["line_items", "contingency_pct", "developer_fee_pct"],
        },
        output_schema={"type": "object"},
    ),
    "export_report": ToolContract(
        name="export_report",
        description="Export a persisted harness report artifact.",
        risk_class=ToolRiskClass.WRITE_INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "report_id": {"type": "string", "minLength": 1},
                "export_format": {"type": "string", "enum": ["markdown", "json"]},
            },
            "required": ["report_id"],
        },
        output_schema={"type": "object"},
    ),
    "search_ordinances": ToolContract(
        name="search_ordinances",
        description="Search locally indexed ordinance chunks and return citation-rich results.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "municipality": {"type": "string", "minLength": 2},
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            "required": ["municipality", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
            },
            "required": ["status", "results"],
        },
    ),
    "fetch_ordinance_section": ToolContract(
        name="fetch_ordinance_section",
        description="Fetch a specific locally indexed ordinance section/chunk by section_id.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "municipality": {"type": "string", "minLength": 2},
                "section_id": {"type": "string", "minLength": 1},
            },
            "required": ["municipality", "section_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "object"},
                "evidence": {"type": "array"},
            },
            "required": ["status", "result"],
        },
    ),
    "search_municode_live": ToolContract(
        name="search_municode_live",
        description="Search Municode live (network) for ordinance sections.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "municipality": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            "required": ["municipality", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
            },
        },
        budget_cents=25,
    ),
    "discover_open_data_layers": ToolContract(
        name="discover_open_data_layers",
        description="Discover ArcGIS Hub/open-data layers for a jurisdiction.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
            },
            "required": ["county", "state", "lat", "lng"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
            },
        },
        budget_cents=25,
    ),
    "discover_municode_authorities": ToolContract(
        name="discover_municode_authorities",
        description="Discover Municode zoning authorities for a county/state.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
            },
            "required": ["county", "state"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
            },
        },
        budget_cents=25,
    ),
    "discover_code_authorities": ToolContract(
        name="discover_code_authorities",
        description=(
            "Discover county ordinance/code providers across Municode, eCode360, "
            "American Legal, Code Publishing, Open Legal Codes, and official county pages."
        ),
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "include_web_fallback": {"type": "boolean"},
            },
            "required": ["county", "state"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
            },
        },
        budget_cents=25,
    ),
    "search_code_authority_live": ToolContract(
        name="search_code_authority_live",
        description="Search a discovered Open Legal Codes jurisdiction for ordinance text.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "jurisdiction_id": {"type": "string", "minLength": 2},
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            "required": ["jurisdiction_id", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
                "message": {"type": "string"},
            },
        },
        budget_cents=25,
    ),
    "web_search": ToolContract(
        name="web_search",
        description="Last-resort web search for sources not present in local data.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        budget_cents=25,
    ),
    "fetch_web_contents": ToolContract(
        name="fetch_web_contents",
        description="Fetch approved public page contents for specific URLs through the shared Exa-backed harness lookup lane.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                    "maxItems": 5,
                }
            },
            "required": ["urls"],
        },
        output_schema={"type": "object"},
        budget_cents=25,
    ),
    "search_properties": ToolContract(
        name="search_properties",
        description="Bulk property search across static and dynamically discovered county datasets.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "city": {"type": "string"},
                "land_use_type": {
                    "type": "string",
                    "enum": [
                        "vacant_residential",
                        "vacant_commercial",
                        "single_family",
                        "multifamily",
                        "commercial",
                        "industrial",
                        "agricultural",
                    ],
                },
                "min_lot_size_sqft": {"type": "number"},
                "max_lot_size_sqft": {"type": "number"},
                "min_sale_price": {"type": "number"},
                "max_sale_price": {"type": "number"},
                "min_assessed_value": {"type": "number"},
                "max_assessed_value": {"type": "number"},
                "year_built_before": {"type": "integer"},
                "year_built_after": {"type": "integer"},
                "owner_name_contains": {"type": "string"},
                "ownership_min_years": {"type": "integer", "minimum": 0},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 2000},
            },
            "required": ["county"],
        },
        output_schema={"type": "object"},
        budget_cents=50,
    ),
    "filter_dataset": ToolContract(
        name="filter_dataset",
        description="Filter/sort the in-session dataset.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    ),
    "get_dataset_info": ToolContract(
        name="get_dataset_info",
        description="Return summary and schema info for the in-session dataset.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    ),
    "generate_document": ToolContract(
        name="generate_document",
        description="Generate an internal report/document artifact (no external write).",
        risk_class=ToolRiskClass.WRITE_INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["evidence_ids"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "artifacts": {"type": "object"},
            },
            "required": ["status"],
        },
    ),
    "draft_google_doc": ToolContract(
        name="draft_google_doc",
        description="Draft a document inside PlotLot (no external write).",
        risk_class=ToolRiskClass.WRITE_INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "draft": {"type": "object"},
                "artifacts": {"type": "object"},
            },
            "required": ["status"],
        },
    ),
    "draft_email": ToolContract(
        name="draft_email",
        description="Draft an outreach email inside PlotLot (no external write).",
        risk_class=ToolRiskClass.WRITE_INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "array", "items": {"type": "string"}},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["to", "subject", "body"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "draft": {"type": "object"},
                "artifacts": {"type": "object"},
            },
            "required": ["status"],
        },
    ),
    "gmail_send_draft": ToolContract(
        name="gmail_send_draft",
        description="Send an email draft via Gmail (external write; approval required).",
        risk_class=ToolRiskClass.WRITE_EXTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "minLength": 1},
            },
            "required": ["draft_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "object"},
                "message": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
    "create_spreadsheet": ToolContract(
        name="create_spreadsheet",
        description="Create a Google Sheets spreadsheet (external write).",
        risk_class=ToolRiskClass.WRITE_EXTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "headers": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
            },
            "required": ["title", "headers", "rows"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "spreadsheet_url": {"type": "string"},
                "title": {"type": "string"},
                "row_count": {"type": "integer"},
            },
            "required": ["status"],
        },
    ),
    "create_document": ToolContract(
        name="create_document",
        description="Create a Google Docs document (external write).",
        risk_class=ToolRiskClass.WRITE_EXTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
            },
            "required": ["title", "content"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "document_url": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
    "export_dataset": ToolContract(
        name="export_dataset",
        description="Export dataset to Google Sheets (external write).",
        risk_class=ToolRiskClass.WRITE_EXTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "include_fields": {"type": "array", "items": {"type": "string"}},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "spreadsheet_url": {"type": "string"},
                "title": {"type": "string"},
                "row_count": {"type": "integer"},
            },
            "required": ["status"],
        },
    ),
}

_TOOL_CONTRACTS.update(full_harness_chat_tool_contracts())


def get_tool_contract(name: str) -> ToolContract:
    """Return a tool contract or raise KeyError."""

    return _TOOL_CONTRACTS[name]


def list_tool_contracts() -> list[ToolContract]:
    return list(_TOOL_CONTRACTS.values())


def tool_exists(name: str) -> bool:
    return name in _TOOL_CONTRACTS


def tool_risk_class(name: str) -> str:
    """Return risk class string suitable for logs/SSE."""

    contract = _TOOL_CONTRACTS.get(name)
    return contract.risk_class if contract else ToolRiskClass.EXECUTION.value


def tool_contract_json(name: str) -> dict[str, Any]:
    """Return a JSON-serializable view of a contract for API/MCP surfaces."""

    contract = get_tool_contract(name)
    return contract.model_dump()
