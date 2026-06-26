"""HTN decomposition of the Kleyman methodology — tasks and methods as data.

An HTN (hierarchical task network) decomposes a high-level task into ordered
sub-tasks via *methods* — named, preconditional decomposition alternatives.
This module expresses the Kleyman step decomposition as data so the planner
(Slice 5.1) can select methods by precondition rather than by prompt hope.

Two layers, kept deliberately separate:

* :mod:`plotlot.domain.steps` — the step enum + the field-key dependency table
  + the blocking rule ("step 5 blocked when ``zoning.*`` not verified_fact").
  This answers: *may this step activate given the current claims?*

* this module (:mod:`plotlot.domain.methodology`) — the decomposition of an
  *activated* step into its named methods (sub-tasks). This answers: *given
  the step is active, which sub-task sequence runs?* A step may have more
  than one method; method selection is by precondition (e.g. step 3 branches
  on ``product.unit_count``: ≥5 units → income approach, ≤4 → comp approach,
  per spec acceptance #4).

Transport-free: pure data + pure functions. No imports from harness/api/tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from plotlot.domain.steps import KleymanStep

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from plotlot.domain.claims import Claim


@dataclass(frozen=True, slots=True)
class HtnMethod:
    """A named decomposition alternative for a step.

    A step may have several methods; the planner picks the first whose
    ``applicable`` predicate holds over the current claim set. ``subtasks``
    is the ordered sequence of named sub-tasks (tool-agnostic labels) the
    planner must execute for this method.

    Residential vs commercial divergence (spec acceptance #4) is encoded as
    two methods on step 3, keyed on ``product.unit_count`` — a typed method
    dispatch, not a prompt hope.

    Attributes:
        name: stable identifier (e.g. ``"step3.income_approach"``).
        step: the :class:`~plotlot.domain.steps.KleymanStep` this method
            decomposes.
        applicable: predicate ``(claims) -> bool``; the planner selects the
            first method (in declaration order) whose predicate holds.
        subtasks: ordered named sub-tasks. These are method-internal labels
            (e.g. ``"fetch_comps"``, ``"compute_noi"``, ``"apply_cap_rate"``);
            the tools package (Slice 4.1) binds them to concrete ToolContracts.
        description: human-readable summary (for traces / reports).
    """

    name: str
    step: KleymanStep
    applicable: "Callable[[Sequence[Claim]], bool]"
    subtasks: tuple[str, ...]
    description: str = ""


# ---------------------------------------------------------------------------
# Method applicability predicates.
#
# Kept as standalone functions (not lambdas) so they're picklable, named in
# traces, and unit-testable in isolation.
# ---------------------------------------------------------------------------


def _unit_count_at_least(threshold: int) -> "Callable[[Sequence[Claim]], bool]":
    """Predicate: the ``product.unit_count`` claim is ≥ ``threshold``.

    Step 3 (stabilized value / as-built value) branches on this: ≥5 units take
    the income approach (NOI/cap), ≤4 take the comp approach (ARV). The
    branch is a typed method dispatch encoded here, not a prompt instruction.
    """

    def predicate(claims: "Sequence[Claim]") -> bool:
        for c in claims:
            if c.field_key != "product.unit_count":
                continue
            try:
                return float(c.value) >= threshold
            except (TypeError, ValueError):
                return False
        return False

    return predicate


def _always(claims: "Sequence[Claim]") -> bool:  # noqa: ARG001
    """Default method: applicable when no more specific method matches."""
    return True


# ---------------------------------------------------------------------------
# The HTN decomposition table.
#
# Declared in step order; within a step, more-specific methods come first so
# the planner's "first applicable wins" rule selects the specialized path
# before the generic fallback.
# ---------------------------------------------------------------------------

_METHODS: tuple[HtnMethod, ...] = (
    HtnMethod(
        name="step1.density_study",
        step=KleymanStep.DENSITY_STUDY,
        applicable=_always,
        subtasks=(
            "geocode_address",
            "lookup_zoning_district",
            "read_dimensional_standard",
            "calculate_max_units",
        ),
        description=(
            "Geocode the parcel, look up its zoning district, read the typed "
            "dimensional standard, and compute the max allowable units."
        ),
    ),
    # Step 3 (as-built value) — two methods, specialized first.
    HtnMethod(
        name="step2.income_approach",
        step=KleymanStep.AS_BUILT_VALUE,
        applicable=_unit_count_at_least(5),
        subtasks=(
            "estimate_market_rent",
            "compute_stabilized_noi",
            "apply_cap_rate",
        ),
        description=(
            "For ≥5 units (multifamily): stabilized value = NOI ÷ market cap "
            "rate. The income approach, not sales comps."
        ),
    ),
    HtnMethod(
        name="step2.comp_approach",
        step=KleymanStep.AS_BUILT_VALUE,
        applicable=_always,
        subtasks=(
            "fetch_comps",
            "compute_adv_per_unit",
            "multiply_adv_by_units",
        ),
        description=("For ≤4 units: as-built value = ADV per unit × unit count, from sales comps."),
    ),
    HtnMethod(
        name="step3.sweat_equity",
        step=KleymanStep.SWEAT_EQUITY,
        applicable=_always,
        subtasks=(
            "sum_total_cost",
            "compare_to_stabilized_value",
            "compute_sweat_equity_pct",
        ),
        description="Total cost vs stabilized value; target ≥20% sweat equity.",
    ),
    HtnMethod(
        name="step4.construction_costs",
        step=KleymanStep.CONSTRUCTION_COSTS,
        applicable=_always,
        subtasks=(
            "load_regional_cost_model",
            "compute_hard_cost",
            "compute_soft_cost",
        ),
        description="Hard $/sqft + soft cost, market-specific via RegionalCostModel.",
    ),
    HtnMethod(
        name="step5.residual_land_value",
        step=KleymanStep.RESIDUAL_LAND_VALUE,
        applicable=_always,
        subtasks=(
            "compute_max_land",
            "subtract_costs_and_financing",
            "subtract_closing",
        ),
        description=(
            "Max land = (SV × 0.80) − hard − soft − financing − closing. "
            "Blocked unless zoning.* is verified_fact (see steps.step_blocked_reasons)."
        ),
    ),
    HtnMethod(
        name="step6.construction_financing",
        step=KleymanStep.CONSTRUCTION_FINANCING,
        applicable=_always,
        subtasks=(
            "size_ltc_loan",
            "compute_io_schedule",
        ),
        description="65–70% LTC, interest-only, 24-month IO period.",
    ),
    HtnMethod(
        name="step7.permanent_financing",
        step=KleymanStep.PERMANENT_FINANCING,
        applicable=_always,
        subtasks=(
            "compute_dscr_constrained_loan",
            "verify_dscr_threshold",
        ),
        description="DSCR-constrained (≥1.25 min), 6.25–6.5%, 30yr amort.",
    ),
    HtnMethod(
        name="step8.investment_criteria",
        step=KleymanStep.INVESTMENT_CRITERIA,
        applicable=_always,
        subtasks=(
            "compute_coc",
            "compute_yield_on_cost",
            "compute_irr",
            "emit_go_no_go",
        ),
        description="CoC ≥5% (go), DSCR ≥1.25, sweat equity ≥20% (strong go).",
    ),
)


def methods_for(step: KleymanStep) -> tuple[HtnMethod, ...]:
    """Return all declared methods for ``step``, in declaration order.

    The planner selects the first applicable one (specialized-first ordering).
    """
    return tuple(m for m in _METHODS if m.step == step)


def select_method(step: KleymanStep, claims: "Sequence[Claim]") -> "HtnMethod | None":
    """Pick the first applicable method for ``step`` over ``claims``.

    Returns ``None`` if the step has no declared methods (a misconfiguration)
    or — currently impossible by construction — if none are applicable (the
    generic ``_always`` fallback is appended last on every step that has one).
    """
    for m in methods_for(step):
        if m.applicable(claims):
            return m
    return None


@dataclass(frozen=True, slots=True)
class MethodDispatch:
    """The result of selecting a method for a step, with breadcrumbs.

    Carries both the selected method and the names of the methods that were
    *skipped* (so a trace can show "income_approach chosen; comp_approach
    was the fallback"). Dispatch is pure: same claims → same selection.
    """

    step: KleymanStep
    selected: "HtnMethod | None"
    skipped: tuple[str, ...] = field(default_factory=tuple)


def dispatch(step: KleymanStep, claims: "Sequence[Claim]") -> MethodDispatch:
    """Pure method dispatch for ``step`` given ``claims``."""
    skipped: list[str] = []
    for m in methods_for(step):
        if m.applicable(claims):
            return MethodDispatch(step=step, selected=m, skipped=tuple(skipped))
        skipped.append(m.name)
    return MethodDispatch(step=step, selected=None, skipped=tuple(skipped))
