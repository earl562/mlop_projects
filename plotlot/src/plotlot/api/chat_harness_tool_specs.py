from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from plotlot.harness.contracts import JsonObject

JsonObjectListAdapter = TypeAdapter(list[JsonObject])

FULL_HARNESS_CHAT_TOOL_NAMES: Final = frozenset(
    {
        "run_deal_analysis",
        "geocode_address",
        "lookup_property_info",
        "search_municode",
        "search_municode_live",
        "get_municode_section",
        "extract_ordinance_rules",
        "search_south_florida_gis",
        "get_gis_source_metadata",
        "query_gis_feature_service",
        "resolve_site_boundary_context",
        "find_comparables",
        "load_rental_market_evidence",
        "load_underwriting_market_profile",
        "discover_rehabvaluator_video_sections",
        "web_search",
        "fetch_web_contents",
        "compute_feasibility",
        "run_noi_valuation",
        "run_pro_forma",
        "run_residual_land_value",
        "run_brrrr_refinance_analysis",
        "run_sensitivity_analysis",
        "create_construction_budget",
        "export_report",
    }
)

FULL_HARNESS_CHAT_TOOLS: Final[list[JsonObject]] = JsonObjectListAdapter.validate_python(
    [
        {
            "type": "function",
            "function": {
                "name": "run_deal_analysis",
                "description": (
                    "Run PlotLot's shared analysis harness end-to-end for an address using the "
                    "same execution path as the harness API and CLI. Use this for the full "
                    "address to parcel/zoning to comps to underwriting workflow."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {"type": "string", "description": "Subject address."},
                        "analysis_type": {
                            "type": "string",
                            "description": "Analysis type such as acquisition_memo or zoning_research.",
                        },
                        "source_mode": {
                            "type": "string",
                            "description": "fixture or live. Live only runs when chat context allows it.",
                        },
                        "assumptions": {
                            "type": "object",
                            "description": "Optional deterministic calculator assumptions.",
                        },
                    },
                    "required": ["address"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "geocode_address",
                "description": (
                    "Resolve an address through the shared harness geocoding tool so downstream "
                    "parcel, zoning, GIS, and comp tools can use the same normalized site context."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {"type": "string", "description": "Subject address."}
                    },
                    "required": ["address"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "lookup_property_info",
                "description": (
                    "Load parcel-adjacent property facts through the shared harness tool, "
                    "including zoning code, lot size, sales history, and parcel geometry when available."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {"type": "string"},
                        "county": {"type": "string"},
                        "state": {"type": "string"},
                        "lat": {"type": "number"},
                        "lng": {"type": "number"},
                    },
                    "required": ["address", "county", "state"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_web_contents",
                "description": (
                    "Fetch public page contents for specific URLs through the shared harness "
                    "web lookup lane. Use this to verify listing pages or other public source pages "
                    "with the same tool path used by the harness runtime."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "One to five public URLs to fetch.",
                        }
                    },
                    "required": ["urls"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_municode",
                "description": (
                    "Search PlotLot's shared Municode fixture/source lane through the harness "
                    "ToolRouter, policy engine, source catalog, and event trace."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "jurisdiction": {
                            "type": "string",
                            "description": "Jurisdiction slug/name.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Regulation search query.",
                        },
                    },
                    "required": ["jurisdiction", "query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_municode_live",
                "description": (
                    "Run live Municode search through the shared harness runtime so chat uses "
                    "the same ordinance lookup lane as the API, CLI, and workers."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "municipality": {"type": "string"},
                        "query": {"type": "string"},
                        "state": {"type": "string"},
                    },
                    "required": ["municipality", "query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_municode_section",
                "description": "Fetch a shared-harness Municode section artifact by section ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "section_id": {
                            "type": "string",
                            "description": "Municode fixture section ID.",
                        }
                    },
                    "required": ["section_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extract_ordinance_rules",
                "description": "Extract deterministic rules from a shared-harness Municode section.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "section_id": {
                            "type": "string",
                            "description": "Municode fixture section ID.",
                        }
                    },
                    "required": ["section_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_south_florida_gis",
                "description": (
                    "Search the shared South Florida GIS source catalog through the harness "
                    "ToolRouter and applicability-aware GIS lane."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "GIS dataset search query."},
                        "county": {
                            "type": "string",
                            "description": "Optional county filter, e.g. Miami-Dade or Broward.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_gis_source_metadata",
                "description": "Inspect a shared South Florida GIS source catalog entry by source ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string", "description": "GIS source ID."}
                    },
                    "required": ["source_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_gis_feature_service",
                "description": (
                    "Query a shared South Florida GIS feature service through the harness GIS lane."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "where": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["source_id", "where"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "resolve_site_boundary_context",
                "description": (
                    "Resolve county and municipal GIS applicability context through the shared "
                    "South Florida GIS lane."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "county": {"type": "string"},
                        "municipality": {"type": "string"},
                    },
                    "required": ["county"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_comparables",
                "description": (
                    "Run PlotLot's shared comparable-sales lane through the harness "
                    "ToolRouter. Use this after parcel lookup to produce cited land comps, "
                    "exit comps, land value range, and ADV-per-unit evidence."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "county": {"type": "string", "description": "County name."},
                        "lat": {"type": "number", "description": "Subject latitude."},
                        "lng": {"type": "number", "description": "Subject longitude."},
                        "address": {
                            "type": "string",
                            "description": "Optional subject address for labeling.",
                        },
                        "state": {
                            "type": "string",
                            "description": "Two-letter state code. Defaults to FL.",
                        },
                        "municipality": {
                            "type": "string",
                            "description": "Optional city/municipality.",
                        },
                        "zoning_code": {
                            "type": "string",
                            "description": "Optional zoning code for downstream context.",
                        },
                        "lot_size_sqft": {
                            "type": "number",
                            "description": "Subject lot size in square feet.",
                        },
                        "radius_miles": {
                            "type": "number",
                            "description": "Comp search radius in miles.",
                        },
                        "months": {
                            "type": "integer",
                            "description": "Recency window in months.",
                        },
                        "max_comps": {
                            "type": "integer",
                            "description": "Maximum comps per comp set.",
                        },
                    },
                    "required": ["county", "lat", "lng"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "load_rental_market_evidence",
                "description": (
                    "Load rental-market evidence through the shared underwriting evidence lane."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "county": {"type": "string"},
                        "municipality": {"type": "string"},
                        "state": {"type": "string"},
                        "property_type": {"type": "string"},
                        "bedrooms": {"type": "number"},
                    },
                    "required": ["county"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "load_underwriting_market_profile",
                "description": (
                    "Load shared market and cost assumptions for underwriting through the harness source lane."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "county": {"type": "string"},
                        "municipality": {"type": "string"},
                        "state": {"type": "string"},
                        "zoning_code": {"type": "string"},
                    },
                    "required": ["county"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "discover_rehabvaluator_video_sections",
                "description": (
                    "Discover public training video/source records through the shared training "
                    "ingestion fixture lane and harness ToolRouter."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Optional public source URL."},
                        "category": {
                            "type": "string",
                            "description": "Optional training category.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compute_feasibility",
                "description": (
                    "Run the shared harness feasibility calculator for density, buildable area, "
                    "estimated units, parking, and feasibility warnings. Use this instead of "
                    "model arithmetic when site or zoning assumptions are provided."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lot_area_sf": {"type": "number"},
                        "max_far": {"type": "number"},
                        "max_units": {"type": "integer"},
                        "parking_spaces_per_unit": {"type": "number"},
                        "efficiency_factor": {"type": "number"},
                        "avg_unit_size_sf": {"type": "number"},
                    },
                    "required": ["lot_area_sf", "efficiency_factor", "avg_unit_size_sf"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_noi_valuation",
                "description": (
                    "Run the shared harness NOI/as-built value calculator. Use for rent, "
                    "vacancy, operating-expense, NOI, cap-rate valuation, and as-built value "
                    "math."
                ),
                "parameters": {
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
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_pro_forma",
                "description": (
                    "Run the shared harness land pro forma calculator for unit-count, "
                    "exit-value, regional-cost, and max-offer underwriting math."
                ),
                "parameters": {
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
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_residual_land_value",
                "description": (
                    "Run the shared harness residual land value calculator for maximum "
                    "supportable land price, spread to asking price, go/no-go signal, and "
                    "warnings."
                ),
                "parameters": {
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
                    "required": ["as_built_value", "desired_profit", "hard_costs"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_brrrr_refinance_analysis",
                "description": (
                    "Run the shared harness BRRRR/refinance calculator for refinance proceeds, "
                    "cash left in deal, debt service, DSCR, cash-on-cash, and cash flow."
                ),
                "parameters": {
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
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_sensitivity_analysis",
                "description": (
                    "Run the shared harness sensitivity calculator for downside/base/upside "
                    "underwriting cases."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "base": {"type": "object"},
                        "value_adjustments_pct": {"type": "array", "items": {"type": "number"}},
                        "cost_adjustments_pct": {"type": "array", "items": {"type": "number"}},
                    },
                    "required": ["base"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_construction_budget",
                "description": (
                    "Run the shared harness construction budget calculator for hard costs, "
                    "soft costs, contingency, total budget, and draw-schedule basis."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "line_items": {"type": "array", "items": {"type": "object"}},
                        "contingency_pct": {"type": "number"},
                        "developer_fee_pct": {"type": "number"},
                    },
                    "required": ["line_items", "contingency_pct", "developer_fee_pct"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "export_report",
                "description": (
                    "Export a persisted harness report artifact through the shared ToolRouter. "
                    "This remains policy-gated and does not finalize unsupported reports."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "report_id": {"type": "string"},
                        "export_format": {"type": "string", "enum": ["markdown", "json"]},
                    },
                    "required": ["report_id"],
                },
            },
        },
    ]
)
