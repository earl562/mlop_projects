from __future__ import annotations

from plotlot.harness.agent_run_responses import AgentRunResponse
from plotlot.harness.agent_run_summary import AgentRunSummaryArtifact
from plotlot.pipeline.lookup_snapshot_json import JsonValue

_REQUIRED_TEXT_FIELDS = (
    "key",
    "current_verified_condition",
    "proposed_scenario",
    "required_zoning_entitlement_path",
    "upside_mechanism",
    "next_verification_step",
)

_REQUIRED_LIST_FIELDS = (
    "calculation_outputs",
    "blocking_constraints",
    "evidence_ids",
    "assumptions",
)


def material_claim_count(artifact: AgentRunSummaryArtifact) -> int:
    return sum(1 for claim in artifact_claims(artifact) if is_material_claim(claim))


def opportunity_hypothesis_count(artifact: AgentRunSummaryArtifact) -> int:
    return len(opportunity_hypotheses(artifact))


def incomplete_opportunity_keys(artifact: AgentRunSummaryArtifact) -> tuple[str, ...]:
    return tuple(
        claim_key(opportunity)
        for opportunity in opportunity_hypotheses(artifact)
        if not opportunity_is_complete(opportunity)
    )


def missing_assumption_keys(
    response: AgentRunResponse,
    artifact: AgentRunSummaryArtifact,
) -> tuple[str, ...]:
    actual = assumption_keys(artifact)
    return tuple(key for key in required_assumption_keys(response) if key not in actual)


def required_assumption_keys(response: AgentRunResponse) -> tuple[str, ...]:
    keys = [
        *(f"open_question.{index}" for index, _ in enumerate(response.open_questions, start=1)),
        *(f"escalation.{index}" for index, _ in enumerate(response.escalations, start=1)),
        *(f"warning.{index}" for index, _ in enumerate(response.warnings, start=1)),
    ]
    return tuple(keys)


def assumption_keys(artifact: AgentRunSummaryArtifact) -> frozenset[str]:
    assumptions = artifact.report_json.get("assumptions")
    if not isinstance(assumptions, list):
        return frozenset()
    return frozenset(
        key
        for assumption in assumptions
        if isinstance(assumption, dict)
        for key in (assumption.get("key"),)
        if isinstance(key, str) and key
    )


def unsupported_claim_keys(artifact: AgentRunSummaryArtifact) -> tuple[str, ...]:
    known_evidence_ids = set(artifact.evidence_ids)
    unsupported: list[str] = []
    for claim in artifact_claims(artifact):
        if not is_material_claim(claim):
            continue
        claim_evidence_ids = claim_evidence_ids_for(claim)
        if not claim_evidence_ids or not set(claim_evidence_ids).issubset(known_evidence_ids):
            unsupported.append(claim_key(claim))
    return tuple(unsupported)


def artifact_claims(
    artifact: AgentRunSummaryArtifact,
) -> tuple[dict[str, JsonValue], ...]:
    return (*section_claims(artifact), *opportunity_claims(artifact))


def section_claims(
    artifact: AgentRunSummaryArtifact,
) -> tuple[dict[str, JsonValue], ...]:
    sections = artifact.report_json.get("sections")
    if not isinstance(sections, list):
        return ()
    claims: list[dict[str, JsonValue]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        raw_claims = section.get("claims")
        if not isinstance(raw_claims, list):
            continue
        claims.extend(claim for claim in raw_claims if isinstance(claim, dict))
    return tuple(claims)


def opportunity_claims(
    artifact: AgentRunSummaryArtifact,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        opportunity
        for opportunity in opportunity_hypotheses(artifact)
        if opportunity.get("status") == "hypothesis"
    )


def opportunity_hypotheses(
    artifact: AgentRunSummaryArtifact,
) -> tuple[dict[str, JsonValue], ...]:
    opportunities = artifact.report_json.get("opportunities")
    if not isinstance(opportunities, list):
        return ()
    return tuple(opportunity for opportunity in opportunities if isinstance(opportunity, dict))


def opportunity_is_complete(opportunity: dict[str, JsonValue]) -> bool:
    if opportunity.get("status") != "hypothesis":
        return False
    if any(not has_text(opportunity, field) for field in _REQUIRED_TEXT_FIELDS):
        return False
    if any(not has_string_list(opportunity, field) for field in _REQUIRED_LIST_FIELDS):
        return False
    confidence = opportunity.get("confidence")
    return isinstance(confidence, int | float) and 0 <= confidence <= 1


def is_material_claim(claim: dict[str, JsonValue]) -> bool:
    return claim.get("material") is not False


def claim_evidence_ids_for(claim: dict[str, JsonValue]) -> tuple[str, ...]:
    raw_evidence_ids = claim.get("evidence_ids")
    if not isinstance(raw_evidence_ids, list):
        return ()
    return tuple(evidence_id for evidence_id in raw_evidence_ids if isinstance(evidence_id, str))


def claim_key(claim: dict[str, JsonValue]) -> str:
    raw_key = claim.get("key")
    if isinstance(raw_key, str) and raw_key:
        return raw_key
    return "unknown_claim"


def has_text(record: dict[str, JsonValue], key: str) -> bool:
    value = record.get(key)
    return isinstance(value, str) and bool(value.strip())


def has_string_list(record: dict[str, JsonValue], key: str) -> bool:
    value = record.get(key)
    return isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value)
