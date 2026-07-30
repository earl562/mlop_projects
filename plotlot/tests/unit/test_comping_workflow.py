from __future__ import annotations

from plotlot.harness.comping_workflow import build_comping_workflow_artifact
from plotlot.harness.contracts import RunId, ToolCall, ToolCallId


def test_comping_workflow_records_source_context_and_blocks_underwriting() -> None:
    workflow = build_comping_workflow_artifact(
        property_payload={
            "address": "45 NW 209 ST",
            "municipality": "Miami Gardens",
            "county": "Miami-Dade",
            "state": "FL",
            "zoning_code": "R-1",
            "lot_size_sqft": 10105.0,
        },
        comps_payload={
            "comparables": [
                {
                    "address": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                    "sale_price": 135000.0,
                    "sale_date": "2025-12-01",
                    "lot_size_sqft": 9000.0,
                    "zoning_code": "R-1",
                    "distance_miles": 4.2,
                    "evidence_id": "ev_land_1",
                }
            ],
            "unit_comparables": [
                {
                    "address": "105 NE 213th St, Miami Gardens, FL 33179",
                    "sale_price": 699000.0,
                    "sale_date": "2026-01-20",
                    "lot_size_sqft": 8250.0,
                    "zoning_code": "R-1",
                    "distance_miles": 1.0,
                    "evidence_id": "ev_exit_1",
                }
            ],
        },
        tool_calls=[
            ToolCall(
                tool_call_id=ToolCallId("tool_lookup"),
                run_id=RunId("run_fixture"),
                event_id=None,
                tool_name="lookup_property_info",
                args={},
                status="completed",
                permission_decision={"allowed": True, "reason": "test"},
            )
        ],
        underwriting_status="blocked_until_underwriting_skill",
    )

    assert workflow["agent_role"] == "comping_analyst"
    assert workflow["subject_context"]["source_tool"] == "lookup_property_info"
    assert workflow["subject_context"]["zoning_code"] == "R-1"
    assert workflow["zoning_context"] == {
        "source_tool": "lookup_property_info",
        "source_field": "property_payload.zoning_code",
        "status": "source_discovered",
        "zoning_code": "R-1",
        "usage": "market_area_and_property_type_filter",
        "official_verification_required": True,
        "is_official_entitlement_evidence": False,
        "next_step": (
            "Verify zoning authority through official ordinance or GIS evidence before entitlement claims."
        ),
    }
    assert workflow["programmatic_reasoning"] == {
        "zoning_context_source": "lookup_property_info",
        "zoning_context_source_field": "property_payload.zoning_code",
        "zoning_context_resolution": "source_discovered",
        "zoning_context_usage": "market_area_and_property_type_filter",
        "zoning_context_is_official_entitlement_evidence": False,
        "zoning_context_must_be_verified_by": "official_ordinance_or_gis_evidence",
        "official_zoning_verification_required": True,
        "comp_search_order": "sold_land_6m_then_12m_then_24m_then_improved_sale_fallback",
        "no_cached_zoning_claim": True,
    }
    assert [entry["purpose"] for entry in workflow["search_plan"]] == [
        "primary_recent_land_comp_search",
        "expanded_recent_land_comp_search",
        "maximum_land_comp_lookback_search",
        "exit_value_new_build_fallback_search",
        "exit_value_renovated_sale_fallback_search",
    ]
    assert workflow["accepted_land_comps"][0]["address"] == (
        "17605 NW 19th Avenue, Miami Gardens, FL 33056"
    )
    assert workflow["accepted_exit_comps"][0]["address"] == (
        "105 NE 213th St, Miami Gardens, FL 33179"
    )
    assert workflow["comping_decision_trace"] == {
        "status": "blocked_until_underwriting_skill",
        "search_phase_reached": "accepted_direct_land_comps",
        "accepted_land_comp_count": 1,
        "accepted_exit_comp_count": 1,
        "contextual_public_listing_count": 0,
        "county_reconciled_public_listing_count": 0,
        "rejected_candidate_count": 0,
        "next_required_action": "handoff_to_underwriting_skill",
        "search_expansion_decisions": [
            {
                "step": 1,
                "purpose": "primary_recent_land_comp_search",
                "search_category": "sold_land",
                "search_window_months": 6,
                "decision": "attempt_or_accept_if_candidates_found",
                "stop_rule": "continue_until_two_local_land_candidates_or_expand_window",
            },
            {
                "step": 2,
                "purpose": "expanded_recent_land_comp_search",
                "search_category": "sold_land",
                "search_window_months": 12,
                "decision": "attempt_or_accept_if_candidates_found",
                "stop_rule": "continue_until_two_local_land_candidates_or_expand_window",
            },
            {
                "step": 3,
                "purpose": "maximum_land_comp_lookback_search",
                "search_category": "sold_land",
                "search_window_months": 24,
                "decision": "attempt_or_accept_if_candidates_found",
                "stop_rule": "continue_to_improved_sale_fallback_if_land_support_is_thin",
            },
            {
                "step": 4,
                "purpose": "exit_value_new_build_fallback_search",
                "search_category": "new_build_houses",
                "search_window_months": 12,
                "decision": "fallback_exit_value_context",
                "stop_rule": "stop_after_one_local_improved_sale_candidate",
            },
            {
                "step": 5,
                "purpose": "exit_value_renovated_sale_fallback_search",
                "search_category": "renovated_houses",
                "search_window_months": 12,
                "decision": "fallback_exit_value_context",
                "stop_rule": "stop_after_one_local_improved_sale_candidate",
            },
        ],
    }
    assert workflow["trust_gates"]["underwriting_status"] == "blocked_until_underwriting_skill"


def test_comping_workflow_handles_missing_zoning_without_cached_answer() -> None:
    workflow = build_comping_workflow_artifact(
        property_payload={
            "address": "123 Example St, Fort Lauderdale, FL 33301",
            "municipality": "Fort Lauderdale",
            "county": "Broward",
            "state": "FL",
            "lot_size_sqft": 7500.0,
        },
        comps_payload={
            "comparables": [],
            "unit_comparables": [],
        },
        tool_calls=[],
    )

    assert workflow["subject_context"]["zoning_code"] == ""
    assert workflow["zoning_context"]["status"] == "missing_from_property_record"
    assert workflow["zoning_context"]["is_official_entitlement_evidence"] is False
    assert workflow["zoning_context"]["official_verification_required"] is True
    assert workflow["programmatic_reasoning"]["no_cached_zoning_claim"] is True
    assert workflow["programmatic_reasoning"]["zoning_context_resolution"] == (
        "missing_from_property_record"
    )
    assert workflow["trust_gates"]["underwriting_status"] == "blocked_missing_land_comp_support"
    assert workflow["comping_decision_trace"]["search_phase_reached"] == "no_land_comps_found"
    assert workflow["comping_decision_trace"]["next_required_action"] == (
        "find_qualified_land_comps_or_user_supplied_market_evidence"
    )
    assert all("R-1" not in entry["query"] for entry in workflow["search_plan"])
