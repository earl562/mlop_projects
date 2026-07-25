from __future__ import annotations

from plotlot.harness.comparable_listing_search import comparable_listing_query_plan
from plotlot.harness.comping_decision_trace import (
    CompingDecisionTraceInput,
    build_comping_decision_trace,
)
from plotlot.harness.contracts import JsonObject, ToolCall


def build_comping_workflow_artifact(
    *,
    property_payload: JsonObject,
    comps_payload: JsonObject,
    tool_calls: list[ToolCall],
    underwriting_status: str | None = None,
) -> JsonObject:
    land_comps = _comp_decisions(
        comps_payload,
        key="comparables",
        decision="accepted_land_comp",
    )
    exit_comps = _comp_decisions(
        comps_payload,
        key="unit_comparables",
        decision="accepted_exit_comp",
    )
    contextual_public_listing_comps = _verified_public_listing_decisions(comps_payload)
    county_reconciled_public_listing_comps = _county_reconciled_public_listing_decisions(
        comps_payload
    )
    zoning_context = _zoning_context(property_payload)
    rejected_candidates = _rejected_candidates(comps_payload)
    search_plan = _search_plan(property_payload=property_payload, comps_payload=comps_payload)
    resolved_underwriting_status = underwriting_status or _underwriting_status(
        accepted_land_comps=land_comps,
        contextual_public_listing_comps=contextual_public_listing_comps,
        county_reconciled_public_listing_comps=county_reconciled_public_listing_comps,
    )
    return {
        "skill_name": "comparable_comping",
        "agent_role": "comping_analyst",
        "subject_context": {
            "source_tool": "lookup_property_info",
            "address": str(property_payload.get("address") or ""),
            "municipality": str(property_payload.get("municipality") or ""),
            "county": str(property_payload.get("county") or ""),
            "state": str(property_payload.get("state") or "FL"),
            "zoning_code": str(property_payload.get("zoning_code") or ""),
            "lot_size_sqft": float(property_payload.get("lot_size_sqft") or 0.0),
        },
        "zoning_context": zoning_context,
        "source_tool_sequence": [call.tool_name for call in tool_calls],
        "programmatic_reasoning": {
            "zoning_context_source": "lookup_property_info",
            "zoning_context_source_field": "property_payload.zoning_code",
            "zoning_context_resolution": zoning_context["status"],
            "zoning_context_usage": "market_area_and_property_type_filter",
            "zoning_context_is_official_entitlement_evidence": False,
            "zoning_context_must_be_verified_by": "official_ordinance_or_gis_evidence",
            "official_zoning_verification_required": True,
            "comp_search_order": "sold_land_6m_then_12m_then_24m_then_improved_sale_fallback",
            "no_cached_zoning_claim": True,
        },
        "search_plan": search_plan,
        "accepted_land_comps": land_comps,
        "accepted_exit_comps": exit_comps,
        "contextual_public_listing_comps": contextual_public_listing_comps,
        "county_reconciled_public_listing_comps": county_reconciled_public_listing_comps,
        "rejected_candidates": rejected_candidates,
        "comping_decision_trace": build_comping_decision_trace(
            CompingDecisionTraceInput(
                status=resolved_underwriting_status,
                search_plan=search_plan,
                accepted_land_comps=land_comps,
                accepted_exit_comps=exit_comps,
                contextual_public_listing_comps=contextual_public_listing_comps,
                county_reconciled_public_listing_comps=county_reconciled_public_listing_comps,
                rejected_candidates=rejected_candidates,
            )
        ),
        "trust_gates": {
            "zoning_context_required": True,
            "parcel_context_required": True,
            "county_reconciliation_required_for_live_public_listings": True,
            "underwriting_status": resolved_underwriting_status,
            "accepted_land_comp_count": len(land_comps),
            "accepted_exit_comp_count": len(exit_comps),
            "contextual_public_listing_count": len(contextual_public_listing_comps),
            "county_reconciled_public_listing_count": len(county_reconciled_public_listing_comps),
        },
    }


def _zoning_context(property_payload: JsonObject) -> JsonObject:
    zoning_code = str(property_payload.get("zoning_code") or "").strip()
    if zoning_code:
        status = "source_discovered"
        next_step = "Verify zoning authority through official ordinance or GIS evidence before entitlement claims."
    else:
        status = "missing_from_property_record"
        next_step = "Resolve zoning from official municipal or county sources before entitlement claims."
    return {
        "source_tool": "lookup_property_info",
        "source_field": "property_payload.zoning_code",
        "status": status,
        "zoning_code": zoning_code,
        "usage": "market_area_and_property_type_filter",
        "official_verification_required": True,
        "is_official_entitlement_evidence": False,
        "next_step": next_step,
    }


def _comp_decisions(comps_payload: JsonObject, *, key: str, decision: str) -> list[JsonObject]:
    candidates = comps_payload.get(key)
    if not isinstance(candidates, list):
        return []
    return [
        {
            "decision": decision,
            "address": str(candidate.get("address") or ""),
            "sale_price": float(candidate.get("sale_price") or 0.0),
            "sale_date": str(candidate.get("sale_date") or ""),
            "lot_size_sqft": float(candidate.get("lot_size_sqft") or 0.0),
            "zoning_code": str(candidate.get("zoning_code") or ""),
            "distance_miles": float(candidate.get("distance_miles") or 0.0),
            "evidence_id": str(candidate.get("evidence_id") or ""),
            "reason": "source_candidate_matches_subject_context",
        }
        for candidate in candidates
        if isinstance(candidate, dict)
    ]


def _search_plan(*, property_payload: JsonObject, comps_payload: JsonObject) -> list[JsonObject]:
    web_listing_search = comps_payload.get("web_listing_search")
    if isinstance(web_listing_search, dict):
        query_plan = web_listing_search.get("query_plan")
        if isinstance(query_plan, list):
            return [entry for entry in query_plan if isinstance(entry, dict)]
    return comparable_listing_query_plan(property_payload)


def _rejected_candidates(comps_payload: JsonObject) -> list[JsonObject]:
    rejected_land = comps_payload.get("rejected_land_comparables")
    rejected: list[JsonObject] = []
    if isinstance(rejected_land, list):
        rejected.extend(
            [
                {
                    "address": str(candidate.get("address") or ""),
                    "reason": "failed_comp_filter",
                }
                for candidate in rejected_land
                if isinstance(candidate, dict)
            ]
        )
    reconciliation = comps_payload.get("contextual_land_listing_reconciliation")
    if not isinstance(reconciliation, dict):
        return rejected
    rejected_reconciliation = reconciliation.get("rejected_candidates")
    if not isinstance(rejected_reconciliation, list):
        return rejected
    rejected.extend(
        [
            {
                "address": str(candidate.get("address_hint") or candidate.get("title") or ""),
                "reason": str(candidate.get("reason") or "county_reconciliation_failed"),
            }
            for candidate in rejected_reconciliation
            if isinstance(candidate, dict)
        ]
    )
    return rejected


def _verified_public_listing_decisions(comps_payload: JsonObject) -> list[JsonObject]:
    verification = comps_payload.get("contextual_land_listing_verification")
    if not isinstance(verification, dict):
        return []
    candidates = verification.get("verified_candidates")
    if not isinstance(candidates, list):
        return []
    return [
        {
            "decision": "contextual_verified_public_listing",
            "address": str(candidate.get("address_hint") or candidate.get("title") or ""),
            "url": str(candidate.get("url") or ""),
            "sale_price": float(candidate.get("sale_price") or 0.0),
            "sale_date": str(candidate.get("sale_date") or ""),
            "lot_size_sqft": float(candidate.get("lot_size_sqft") or 0.0),
            "fit_score": float(candidate.get("fit_score") or 0.0),
            "reason": "public_listing_content_verified_but_not_county_reconciled",
        }
        for candidate in candidates
        if isinstance(candidate, dict)
    ]


def _county_reconciled_public_listing_decisions(comps_payload: JsonObject) -> list[JsonObject]:
    reconciliation = comps_payload.get("contextual_land_listing_reconciliation")
    if not isinstance(reconciliation, dict):
        return []
    candidates = reconciliation.get("reconciled_candidates")
    if not isinstance(candidates, list):
        return []
    return [
        {
            "decision": "county_reconciled_public_listing",
            "address": str(candidate.get("address_hint") or candidate.get("title") or ""),
            "url": str(candidate.get("url") or ""),
            "county_folio": str(candidate.get("county_folio") or ""),
            "county_sale_price": float(candidate.get("county_sale_price") or 0.0),
            "county_sale_date": str(candidate.get("county_sale_date") or ""),
            "county_lot_size_sqft": float(candidate.get("county_lot_size_sqft") or 0.0),
            "reason": "public_listing_reconciled_to_county_property_record",
        }
        for candidate in candidates
        if isinstance(candidate, dict)
    ]


def _underwriting_status(
    *,
    accepted_land_comps: list[JsonObject],
    contextual_public_listing_comps: list[JsonObject],
    county_reconciled_public_listing_comps: list[JsonObject],
) -> str:
    if accepted_land_comps or county_reconciled_public_listing_comps:
        return "available_to_underwriting"
    if contextual_public_listing_comps:
        return "blocked_pending_county_reconciliation"
    return "blocked_missing_land_comp_support"
