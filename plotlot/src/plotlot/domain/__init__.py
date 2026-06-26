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

__all__ = [
    "Claim",
    "ClaimKind",
    "ClaimOrigin",
    "DistrictDimensionalStandard",
    "SourceBoundaryViolation",
    "extract_dimensional_standards",
    "source_boundary_ok",
]
