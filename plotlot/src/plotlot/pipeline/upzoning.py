"""Upzoning / subdivision value-creation engine — the developer's "buy the gap".

PlotLot's density calculator answers "what can I build by-right?" This module
answers the question that actually makes land developers money: "what is the GAP
between what this parcel is zoned for NOW and what I can legally make it BECOME —
and how much equity does closing that gap create, before building anything?"

A worked example (Daniel Clayman's case study): a half-acre parcel splits into 5
fee-simple lots by-right, but a special-use permit allows 12. At ~$90k/lot the
upzoned site is worth $1.08M against a $657k all-in basis — $423k of instant
equity created by the entitlement, not by construction. That delta is invisible
to a by-right-only tool.

The core moves, all deterministic (no LLM, no I/O):
  * ``subdivision_lot_yield`` — how many conforming fee-simple lots a parcel
    splits into, gated by min lot AREA and (when known) min lot WIDTH/frontage.
  * ``analyze_upzoning`` — compare a baseline (as-is by-right) scenario to an
    upzoned target, computing each scenario's gross value and the INSTANT EQUITY
    (gross value − all-in basis) the entitlement creates, plus exit options.

Honesty constraints (anti-hallucination doctrine):
  * The per-lot/unit finished value is an INPUT (comps or caller override), never
    fabricated — there is no free sold-lot price source. When it is missing the
    equity is left uncomputed and flagged, not guessed.
  * The upzoned target is caller-supplied (a scenario the user is testing), never
    invented by the model.
"""

from __future__ import annotations

import math

from plotlot.core.types import UpzoningAnalysis, UpzoningScenario
from plotlot.observability.tracing import trace


def subdivision_lot_yield(
    lot_sqft: float,
    min_lot_area_sqft: float,
    *,
    min_lot_width_ft: float | None = None,
    lot_frontage_ft: float | None = None,
) -> tuple[int, str]:
    """Conforming fee-simple lot count for a parcel.

    The binding constraint is the MINIMUM of the area-based yield (lot ÷ min lot
    area) and — when both a min lot width and the parcel's street frontage are
    known — the frontage-based yield (frontage ÷ min lot width). Lot subdivision
    is gated by these dimensional minimums, which is a different calculation from
    dwelling-unit density on a single lot.

    Returns ``(lots, formula)``; ``(0, …)`` when inputs are insufficient.
    """
    if lot_sqft <= 0 or min_lot_area_sqft <= 0:
        return 0, "Insufficient data: a positive lot size and minimum lot area are required."

    area_yield = math.floor(lot_sqft / min_lot_area_sqft)
    parts = [f"{lot_sqft:,.0f} sqft ÷ {min_lot_area_sqft:,.0f} sqft/lot = {area_yield}"]
    lots = area_yield

    if min_lot_width_ft and min_lot_width_ft > 0 and lot_frontage_ft and lot_frontage_ft > 0:
        frontage_yield = math.floor(lot_frontage_ft / min_lot_width_ft)
        parts.append(
            f"frontage {lot_frontage_ft:,.0f} ft ÷ {min_lot_width_ft:,.0f} ft/lot = {frontage_yield}"
        )
        lots = min(area_yield, frontage_yield)

    formula = "; ".join(parts) + f" → {max(0, lots)} conforming lot(s)"
    return max(0, lots), formula


def _build_scenario(
    name: str,
    yield_count: int,
    yield_basis: str,
    value_per_yield: float,
    all_in_basis: float,
    *,
    is_baseline: bool,
    formula: str,
) -> UpzoningScenario:
    """Assemble one scenario's value + instant equity from a resolved yield."""
    value = max(0.0, value_per_yield)
    gross = yield_count * value
    return UpzoningScenario(
        name=name,
        yield_count=yield_count,
        yield_basis=yield_basis,
        value_per_yield=value,
        gross_value=gross,
        instant_equity=gross - all_in_basis,
        is_baseline=is_baseline,
        formula=formula,
    )


def _resolve_yield(
    direct: int | None,
    min_lot_area_sqft: float | None,
    lot_sqft: float,
    yield_basis: str,
    *,
    min_lot_width_ft: float | None,
    lot_frontage_ft: float | None,
) -> tuple[int, str]:
    """Resolve a scenario yield: an explicit count wins; else derive from min lot area."""
    if direct is not None and direct > 0:
        return int(direct), f"{int(direct)} {yield_basis} (provided)"
    if min_lot_area_sqft and min_lot_area_sqft > 0:
        return subdivision_lot_yield(
            lot_sqft,
            min_lot_area_sqft,
            min_lot_width_ft=min_lot_width_ft,
            lot_frontage_ft=lot_frontage_ft,
        )
    return 0, ""


def _exit_options(upzoned: UpzoningScenario, all_in_basis: float) -> list[str]:
    """Deterministic monetization framings derived from the upzoned scenario.

    Mirrors how a developer actually thinks about disposition: flip the entitled
    lots, assign the contract, sell enough lots to recover basis and keep the rest
    as "free" land, or build it all out.
    """
    n = upzoned.yield_count
    v = upzoned.value_per_yield
    gross = upzoned.gross_value
    basis = upzoned.yield_basis
    if n <= 0 or v <= 0:
        return []

    options = [
        f"Flip all {n} {basis}: sell at ${v:,.0f} each = ${gross:,.0f} gross, "
        f"netting ~${gross - all_in_basis:,.0f} over your ${all_in_basis:,.0f} basis.",
        f"Assign / double-close the contract — capture the ~${gross - all_in_basis:,.0f} "
        "entitlement spread without closing on construction.",
    ]

    # Partial sale → "free" land: sell enough lots to recover the all-in basis,
    # keep the remainder (you now own them at zero net cost) and pledge them as
    # equity for a construction loan.
    if all_in_basis > 0:
        lots_to_recover = min(n, math.ceil(all_in_basis / v))
        remaining = n - lots_to_recover
        if remaining > 0:
            recovered = lots_to_recover * v
            options.append(
                f"Sell {lots_to_recover} {basis} (~${recovered:,.0f}) to recover your "
                f"${all_in_basis:,.0f} basis, keep the remaining {remaining} for free, then "
                "pledge those as equity for a construction loan (lenders size to appraised "
                "value, not your basis)."
            )
    options.append(
        f"Develop all {n} {basis} yourself for the full development margin — highest total "
        "return, longest timeline and capital commitment."
    )
    return options


@trace(name="analyze_upzoning", span_type="TOOL")
def analyze_upzoning(
    *,
    lot_sqft: float,
    value_per_lot: float | None,
    purchase_price: float = 0.0,
    entitlement_soft_costs: float = 0.0,
    value_source: str = "override",
    baseline_yield: int | None = None,
    upzoned_yield: int | None = None,
    baseline_min_lot_area_sqft: float | None = None,
    upzoned_min_lot_area_sqft: float | None = None,
    yield_basis: str = "buildable lots",
    min_lot_width_ft: float | None = None,
    lot_frontage_ft: float | None = None,
) -> UpzoningAnalysis:
    """Compare a by-right baseline to an upzoned target and price the equity created.

    Provide each scenario's yield either directly (``baseline_yield`` /
    ``upzoned_yield``) or as a minimum lot area to subdivide against
    (``*_min_lot_area_sqft``). ``value_per_lot`` is the finished sale value per
    lot/unit — required for the equity math and never fabricated.

    Returns an ``UpzoningAnalysis`` with both scenarios, the value uplift, the
    instant equity, cost per lot, and deterministic exit options. When
    ``value_per_lot`` is missing the yields are still returned but equity is left
    at zero with a warning.
    """
    all_in_basis = max(0.0, purchase_price) + max(0.0, entitlement_soft_costs)
    warnings: list[str] = []
    notes: list[str] = []

    b_yield, b_formula = _resolve_yield(
        baseline_yield,
        baseline_min_lot_area_sqft,
        lot_sqft,
        yield_basis,
        min_lot_width_ft=min_lot_width_ft,
        lot_frontage_ft=lot_frontage_ft,
    )
    u_yield, u_formula = _resolve_yield(
        upzoned_yield,
        upzoned_min_lot_area_sqft,
        lot_sqft,
        yield_basis,
        min_lot_width_ft=min_lot_width_ft,
        lot_frontage_ft=lot_frontage_ft,
    )

    value_missing = value_per_lot is None or value_per_lot <= 0
    effective_value = (
        float(value_per_lot) if value_per_lot is not None and value_per_lot > 0 else 0.0
    )
    resolved_source = "missing" if value_missing else value_source

    if value_missing:
        warnings.append(
            "No finished per-lot value provided — instant equity cannot be computed. "
            "Supply a per-lot sale value from local comps or a broker (there is no free "
            "sold-lot price source)."
        )
    elif value_source not in ("comps", "override"):
        notes.append(
            f"Per-lot value source '{value_source}' — treat as an estimate, not appraised."
        )

    baseline = (
        _build_scenario(
            "By-right (as-is)",
            b_yield,
            yield_basis,
            effective_value,
            all_in_basis,
            is_baseline=True,
            formula=b_formula,
        )
        if b_yield > 0
        else None
    )
    upzoned = (
        _build_scenario(
            "Upzoned / subdivided (target)",
            u_yield,
            yield_basis,
            effective_value,
            all_in_basis,
            is_baseline=False,
            formula=u_formula,
        )
        if u_yield > 0
        else None
    )

    if upzoned is None:
        warnings.append(
            "No upzoned target yield resolved — provide an upzoned yield or a target "
            "minimum lot area to compare against."
        )

    analysis = UpzoningAnalysis(
        purchase_price=purchase_price,
        entitlement_soft_costs=entitlement_soft_costs,
        all_in_basis=all_in_basis,
        value_source=resolved_source,
        baseline=baseline,
        upzoned=upzoned,
        notes=notes,
        warnings=warnings,
    )

    if upzoned is not None:
        # cost_per_yield is value-independent (basis ÷ lots) so it's always useful.
        if upzoned.yield_count > 0:
            analysis.cost_per_yield = all_in_basis / upzoned.yield_count
        # Equity / uplift / exits depend on a real per-lot value — when it is
        # missing they stay at their zero defaults rather than reporting a
        # misleading "−basis" loss the data can't support.
        if not value_missing:
            analysis.equity_created = upzoned.instant_equity
            if baseline is not None:
                analysis.value_uplift = upzoned.gross_value - baseline.gross_value
            analysis.exit_options = _exit_options(upzoned, all_in_basis)

    return analysis
