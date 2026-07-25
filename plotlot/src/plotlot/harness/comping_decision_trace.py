from __future__ import annotations

from dataclasses import dataclass

from plotlot.harness.contracts import JsonObject


@dataclass(frozen=True, slots=True)
class CompingDecisionTraceInput:
    status: str
    search_plan: list[JsonObject]
    accepted_land_comps: list[JsonObject]
    accepted_exit_comps: list[JsonObject]
    contextual_public_listing_comps: list[JsonObject]
    county_reconciled_public_listing_comps: list[JsonObject]
    rejected_candidates: list[JsonObject]


def build_comping_decision_trace(trace_input: CompingDecisionTraceInput) -> JsonObject:
    return {
        "status": trace_input.status,
        "search_phase_reached": _search_phase_reached(trace_input),
        "accepted_land_comp_count": len(trace_input.accepted_land_comps),
        "accepted_exit_comp_count": len(trace_input.accepted_exit_comps),
        "contextual_public_listing_count": len(trace_input.contextual_public_listing_comps),
        "county_reconciled_public_listing_count": len(
            trace_input.county_reconciled_public_listing_comps
        ),
        "rejected_candidate_count": len(trace_input.rejected_candidates),
        "next_required_action": _next_required_action(trace_input.status),
        "search_expansion_decisions": _search_expansion_decisions(trace_input.search_plan),
    }


def _search_phase_reached(trace_input: CompingDecisionTraceInput) -> str:
    if trace_input.accepted_land_comps:
        return "accepted_direct_land_comps"
    if trace_input.county_reconciled_public_listing_comps:
        return "accepted_county_reconciled_public_listing_comps"
    match trace_input.status:
        case "blocked_pending_county_reconciliation":
            return "pending_county_reconciliation"
        case "blocked_missing_land_comp_support":
            return "no_land_comps_found"
        case "blocked_until_underwriting_skill":
            return "comping_complete_waiting_for_underwriting"
        case "available_to_underwriting":
            return "available_to_underwriting"
        case _:
            return "requires_review"


def _next_required_action(status: str) -> str:
    match status:
        case "available_to_underwriting":
            return "run_underwriting_with_verified_comp_support"
        case "blocked_pending_county_reconciliation":
            return "reconcile_public_listing_candidates_to_county_records"
        case "blocked_missing_land_comp_support":
            return "find_qualified_land_comps_or_user_supplied_market_evidence"
        case "blocked_until_underwriting_skill":
            return "handoff_to_underwriting_skill"
        case _:
            return "review_comping_workflow_status"


def _search_expansion_decisions(search_plan: list[JsonObject]) -> list[JsonObject]:
    return [
        {
            "step": entry.get("step"),
            "purpose": str(entry.get("purpose") or ""),
            "search_category": str(entry.get("search_category") or ""),
            "search_window_months": entry.get("search_window_months"),
            "decision": _search_step_decision(str(entry.get("search_category") or "")),
            "stop_rule": str(entry.get("stop_rule") or ""),
        }
        for entry in search_plan
    ]


def _search_step_decision(search_category: str) -> str:
    match search_category:
        case "sold_land":
            return "attempt_or_accept_if_candidates_found"
        case "new_build_houses" | "renovated_houses":
            return "fallback_exit_value_context"
        case _:
            return "review_search_category"
