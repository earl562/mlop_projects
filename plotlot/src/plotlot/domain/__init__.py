"""PlotLot domain layer — typed contracts for the agentic harness.

The domain layer is transport-free: pure data + rules. It encodes the
Kleyman 8-step methodology as typed claims, steps, and guardrails, plus
the evidence-foundation types (dimensional standards, etc.) the agent
reasons over.

Nothing in `domain/` imports from harness/, api/, tools/, or retrieval/.
"""

from plotlot.domain.claims import (
    ASSUMPTION_NAMESPACES,
    LOCAL_AUTHORITY_NAMESPACES,
    Claim,
    ClaimKind,
    ClaimOrigin,
    SourceBoundaryViolation,
    source_boundary_ok,
)
from plotlot.domain.dimensional_standard import (
    DistrictDimensionalStandard,
    extract_dimensional_standards,
)
from plotlot.domain.guardrails import (
    GuardrailRule,
    GuardrailViolation,
    check_assumption_namespace,
    check_contradiction_review,
    check_hypothesis_verification,
    check_local_authority_origin,
    check_material_evidence,
    evaluate_guardrails,
    human_review_violations,
    integrity_violations,
    is_material,
    requires_human_review,
)
from plotlot.domain.methodology import (
    HtnMethod,
    MethodDispatch,
    dispatch,
    methods_for,
    select_method,
)
from plotlot.domain.steps import (
    KleymanStep,
    StepDef,
    StepRequirement,
    all_steps,
    requirement_satisfied,
    step_blocked_reasons,
    step_can_activate,
    step_def,
)
from plotlot.domain.types import (
    DEFAULT_ORDINANCE_LEGAL_CAVEAT,
    EvidenceBackedReportSection,
    EvidenceCitation,
    EvidenceConfidence,
    EvidenceItem,
    PolicyDecision,
    ReportClaim,
    SourceType,
    ToolContext,
    ToolContract,
    ToolRiskClass,
)

__all__ = [
    "ASSUMPTION_NAMESPACES",
    "LOCAL_AUTHORITY_NAMESPACES",
    "Claim",
    "ClaimKind",
    "ClaimOrigin",
    "DEFAULT_ORDINANCE_LEGAL_CAVEAT",
    "DistrictDimensionalStandard",
    "EvidenceBackedReportSection",
    "EvidenceCitation",
    "EvidenceConfidence",
    "EvidenceItem",
    "GuardrailRule",
    "GuardrailViolation",
    "HtnMethod",
    "KleymanStep",
    "LOCAL_AUTHORITY_NAMESPACES",
    "MethodDispatch",
    "PolicyDecision",
    "ReportClaim",
    "SourceType",
    "SourceBoundaryViolation",
    "StepDef",
    "StepRequirement",
    "ToolContext",
    "ToolContract",
    "ToolRiskClass",
    "all_steps",
    "check_assumption_namespace",
    "check_contradiction_review",
    "check_hypothesis_verification",
    "check_local_authority_origin",
    "check_material_evidence",
    "dispatch",
    "evaluate_guardrails",
    "extract_dimensional_standards",
    "human_review_violations",
    "integrity_violations",
    "is_material",
    "methods_for",
    "requirement_satisfied",
    "requires_human_review",
    "select_method",
    "source_boundary_ok",
    "step_blocked_reasons",
    "step_can_activate",
    "step_def",
]
