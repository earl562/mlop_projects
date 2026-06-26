"""PlotLot domain layer — typed contracts for the agentic harness.

The domain layer is transport-free: pure data + rules. It encodes the
Kleyman 8-step methodology as typed claims, steps, and guardrails, plus
the evidence-foundation types (dimensional standards, etc.) the agent
reasons over.

Nothing in `domain/` imports from harness/, api/, tools/, or retrieval/.
"""

from plotlot.domain.claims import (
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

__all__ = [
    "Claim",
    "ClaimKind",
    "ClaimOrigin",
    "DistrictDimensionalStandard",
    "HtnMethod",
    "KleymanStep",
    "MethodDispatch",
    "SourceBoundaryViolation",
    "StepDef",
    "StepRequirement",
    "all_steps",
    "dispatch",
    "extract_dimensional_standards",
    "methods_for",
    "requirement_satisfied",
    "select_method",
    "source_boundary_ok",
    "step_blocked_reasons",
    "step_can_activate",
    "step_def",
]
