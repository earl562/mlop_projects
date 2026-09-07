"""Kleyman 8-step methodology — steps as data, with field-key dependencies.

The 8 steps are Daniel Clayman's land-development underwriting sequence
(density study → as-built value → sweat equity → construction costs →
residual land value → construction financing → permanent financing →
investment criteria). Each step is a typed record carrying:

* its position (1..8),
* the field-key namespaces it **produces** (so downstream steps know what to
  expect), and
* the field-key namespaces it **requires** to be at a given epistemic status
  before it may activate (HTN preconditions). A step whose precondition is not
  satisfied is *blocked* — the planner refuses to activate it.

The load-bearing rule (spec acceptance #3): step 5 (residual land value) is
blocked unless every ``zoning.*`` field it transitively depends on is
``kind=verified_fact``. Density study (step 1) precedes land valuation,
enforced by code — not a prompt hope.

This module is transport-free: pure data + pure functions over ``Claim[]``.
Nothing here imports from harness/, api/, tools/, or retrieval/.

Slice 2.2 — step table + the blocking rule. Later slices (`methodology.py`,
`guardrails.py`) build guardrails and planner rules *over* this table.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from plotlot.domain.claims import Claim, ClaimKind

if TYPE_CHECKING:
    from collections.abc import Sequence


class KleymanStep(IntEnum):
    """The 8-step land-development underwriting methodology (in order).

    Ordering is the HTN decomposition order: step N decomposes before step N+1.
    ``IntEnum`` so step dependencies can be expressed as ``step < other`` and
    so the table below can be sorted by step number.
    """

    DENSITY_STUDY = 1  # zoning lookup + max-units calculator
    AS_BUILT_VALUE = 2  # GDV: comps (≤4u) or income approach (≥5u)
    SWEAT_EQUITY = 3  # total cost vs stabilized value, ≥20% target
    CONSTRUCTION_COSTS = 4  # hard + soft, market-specific
    RESIDUAL_LAND_VALUE = 5  # max land = (SV × 0.80) − costs − financing − closing
    CONSTRUCTION_FINANCING = 6  # 65–70% LTC, IO, 24-month
    PERMANENT_FINANCING = 7  # DSCR-constrained, 30yr amort
    INVESTMENT_CRITERIA = 8  # CoC, DSCR, sweat equity, go/no-go


@dataclass(frozen=True, slots=True)
class StepRequirement:
    """A precondition on a step's activation.

    ``field_namespace`` is the prefix before the first ``.`` of a field key
    (e.g. ``"zoning"``, ``"parcel"``, ``"cost"``). ``min_kind`` is the *least*
    epistemic status required (per the verification ladder in
    :class:`~plotlot.domain.claims.ClaimKind`). A requirement is satisfied by a
    claim set if **some** claim with that namespace exists at a status at or
    above ``min_kind``.

    The verification ladder (least → most verified):
    hypothesis → assumption → verified_fact
    (calculation/contradiction are not on this ladder; they're handled
    separately — a calculation inherits the trust of its inputs, a
    contradiction is terminal.)
    """

    field_namespace: str
    min_kind: ClaimKind


@dataclass(frozen=True, slots=True)
class StepDef:
    """A step of the Kleyman methodology, with its typed dependencies.

    Attributes:
        step: the :class:`KleymanStep`.
        produces: field-key namespaces this step is responsible for asserting
            (e.g. step 1 produces ``zoning.*`` and ``product.unit_count``).
            Used by the planner to route "I need X" requests to the right step.
        requires: preconditions — each must be satisfied by the current claim
            set before this step may activate. A step with an unsatisfied
            requirement is *blocked* (see :func:`step_blocked_reasons`).
    """

    step: KleymanStep
    produces: tuple[str, ...]
    requires: tuple[StepRequirement, ...]


# The verification ladder, least → most verified. A claim at rung N satisfies
# a requirement at rung N or below. hypothesis is the floor, verified_fact
# the ceiling. (calculation/contradiction are off-ladder; they never satisfy
# an "at least X" precondition on their own — a calculation must trace to
# verified inputs, a contradiction blocks its whole namespace.)
_KIND_LADDER: tuple[ClaimKind, ...] = (
    ClaimKind.HYPOTHESIS,
    ClaimKind.ASSUMPTION,
    ClaimKind.VERIFIED_FACT,
)


def _ladder_rank(kind: ClaimKind) -> int:
    """Position on the verification ladder, or -1 if off-ladder."""
    try:
        return _KIND_LADDER.index(kind)
    except ValueError:
        return -1


# ---------------------------------------------------------------------------
# The step table — HTN task/method defs as data.
#
# Each step's `requires` encodes the Kleyman ordering invariant:
#   - Step 2 (as-built value) needs step 1's zoning facts (density drives units
#     → units drive GDV).
#   - Step 5 (residual land value) needs zoning.* verified (spec acceptance #3,
#     the load-bearing rule) AND a stabilized value (step 2's output) AND
#     construction costs (step 4's output).
#   - Steps 6/7 need step 5's max land value (loan sizes derive from it).
#   - Step 8 (go/no-go) synthesizes everything.
#
# `produces` documents which field-key namespaces each step owns; the planner
# (Slice 5.1) reads it to decide which step services a "give me X" request.
# ---------------------------------------------------------------------------

_STEPS: tuple[StepDef, ...] = (
    StepDef(
        step=KleymanStep.DENSITY_STUDY,
        produces=("zoning", "product.unit_count"),
        requires=(),
    ),
    StepDef(
        step=KleymanStep.AS_BUILT_VALUE,
        produces=("value.stabilized", "value.gdv", "comp"),
        requires=(
            # Units drive the GDV path; zoning must be verified (not assumed)
            # before we value the as-built — a guessed district can't value a deal.
            StepRequirement("zoning", ClaimKind.VERIFIED_FACT),
        ),
    ),
    StepDef(
        step=KleymanStep.SWEAT_EQUITY,
        produces=("metrics.sweat_equity",),
        requires=(
            StepRequirement("value", ClaimKind.ASSUMPTION),
            StepRequirement("cost", ClaimKind.ASSUMPTION),
        ),
    ),
    StepDef(
        step=KleymanStep.CONSTRUCTION_COSTS,
        produces=("cost",),
        requires=(StepRequirement("zoning", ClaimKind.VERIFIED_FACT),),
    ),
    StepDef(
        step=KleymanStep.RESIDUAL_LAND_VALUE,
        produces=("value.max_land", "value.residual_land"),
        requires=(
            # THE LOAD-BEARING RULE (spec acceptance #3):
            # residual land value cannot be computed on an unverified zoning
            # fact — density (step 1) must precede land valuation, and the
            # zoning.* inputs must be verified_fact, not assumption-grade.
            StepRequirement("zoning", ClaimKind.VERIFIED_FACT),
            StepRequirement("value", ClaimKind.ASSUMPTION),
            StepRequirement("cost", ClaimKind.ASSUMPTION),
        ),
    ),
    StepDef(
        step=KleymanStep.CONSTRUCTION_FINANCING,
        produces=("financing.construction",),
        requires=(
            StepRequirement("value", ClaimKind.ASSUMPTION),
            StepRequirement("cost", ClaimKind.ASSUMPTION),
        ),
    ),
    StepDef(
        step=KleymanStep.PERMANENT_FINANCING,
        produces=("financing.permanent", "metrics.dscr"),
        requires=(StepRequirement("value", ClaimKind.ASSUMPTION),),
    ),
    StepDef(
        step=KleymanStep.INVESTMENT_CRITERIA,
        produces=("recommendation.go_no_go", "metrics.coc", "metrics.yield_on_cost"),
        requires=(
            StepRequirement("value", ClaimKind.ASSUMPTION),
            StepRequirement("cost", ClaimKind.ASSUMPTION),
            StepRequirement("financing", ClaimKind.ASSUMPTION),
        ),
    ),
)


def step_def(step: KleymanStep) -> StepDef:
    """Look up the typed definition for ``step``.

    Every enum member has exactly one definition; a missing entry is a
    programmer error (the table is exhaustive by construction).
    """
    for sd in _STEPS:
        if sd.step == step:
            return sd
    raise KeyError(f"no StepDef for {step!r} — table is not exhaustive")


def all_steps() -> tuple[StepDef, ...]:
    """Return all step definitions, ordered by step number (HTN order)."""
    return _STEPS


# ---------------------------------------------------------------------------


def requirement_satisfied(req: StepRequirement, claims: "Sequence[Claim]") -> bool:
    """Does the claim set satisfy ``req``?

    A requirement is satisfied if **some** claim in ``claims`` has a field_key
    whose namespace matches ``req.field_namespace`` **and** whose kind is at or
    above ``req.min_kind`` on the verification ladder.

    Off-ladder kinds (calculation, contradiction) do not satisfy a requirement
    on their own: a calculation inherits the trust of its inputs (it must
    trace to a verified/assumption input, which itself appears as a claim),
    and a contradiction is terminal (its namespace is in dispute, not settled).
    """
    target_rank = _ladder_rank(req.min_kind)
    if target_rank < 0:
        # A precondition pinned to an off-ladder kind is misconfigured.
        return False
    for c in claims:
        if c.namespace != req.field_namespace:
            continue
        rank = _ladder_rank(c.kind)
        if rank < 0:
            continue  # calculation/contradiction don't satisfy on their own
        if rank >= target_rank:
            return True
    return False


def step_blocked_reasons(step: KleymanStep, claims: "Sequence[Claim]") -> tuple[str, ...]:
    """Return the namespaces whose requirements are unsatisfied for ``step``.

    Empty tuple → the step may activate. Non-empty → the planner must NOT
    activate the step; each element names a blocked namespace (so the agent
    can report *what* is missing, not just *that* something is).

    This is the Kleyman ordering invariant, enforced by code: step 5 blocks
    when ``zoning.*`` is not ``verified_fact`` (spec acceptance #3).
    """
    sd = step_def(step)
    blocked: list[str] = []
    for req in sd.requires:
        if not requirement_satisfied(req, claims):
            blocked.append(req.field_namespace)
    return tuple(blocked)


def step_can_activate(step: KleymanStep, claims: "Sequence[Claim]") -> bool:
    """Convenience: True iff :func:`step_blocked_reasons` is empty."""
    return not step_blocked_reasons(step, claims)
