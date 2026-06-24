"""Deal metrics calculator — pure functions for underwriting go/no-go decisions.

Computes cash-on-cash return, debt service coverage ratio, and sweat equity
from monthly NOI, debt service, cash invested, as-built value, and total cost.

All functions are deterministic, zero-I/O, and operate on DealMetrics from
plotlot.core.types.  Designed as the final step in the Wave 2 pipeline:
pro forma → financing → comps → deal metrics.
"""

from __future__ import annotations

from plotlot.core.types import DealMetrics


# ---------------------------------------------------------------------------
# Core calculator
# ---------------------------------------------------------------------------


def calculate_deal_metrics(
    monthly_noi: float,
    monthly_debt_service: float,
    cash_invested: float,
    as_built_value: float,
    total_cost: float,
) -> DealMetrics:
    """Calculate key underwriting metrics from monthly inputs.

    Args:
        monthly_noi: Stabilized monthly net operating income ($).
        monthly_debt_service: Monthly debt payment ($).
        cash_invested: Total cash/equity invested ($).
        as_built_value: Estimated market value post-construction ($).
        total_cost: Total project cost — land + hard + soft + carry ($).

    Returns:
        DealMetrics populated with:
        - levered_cash_on_cash: Year-1 cash-on-cash return (%).
        - dscr: Debt service coverage ratio (unitless).
        - gross_profit: Sweat equity in dollars = ABV - total_cost.
        - notes: Includes sweat equity percentage for downstream use.

    Formulas
    --------
    Cash-on-Cash  = ((monthly_noi - monthly_debt_service) * 12) / cash_invested * 100
    DSCR          = monthly_noi / monthly_debt_service
    Sweat Equity  = (as_built_value - total_cost) / as_built_value * 100

    Edge cases: division-by-zero returns 0.0 for the affected metric.
    Negative inputs produce meaningful negative metrics.
    """
    annual_cash_flow = (monthly_noi - monthly_debt_service) * 12.0

    # Cash-on-Cash return (%)
    coc: float = 0.0
    if cash_invested > 0:
        coc = (annual_cash_flow / cash_invested) * 100.0

    # Debt Service Coverage Ratio
    dscr: float = 0.0
    if monthly_debt_service > 0:
        dscr = monthly_noi / monthly_debt_service

    # Sweat equity — dollar & percentage
    gross_profit: float = 0.0
    sweat_equity_pct: float = 0.0
    if as_built_value > 0:
        gross_profit = as_built_value - total_cost
        sweat_equity_pct = (gross_profit / as_built_value) * 100.0
    else:
        gross_profit = -total_cost  # negative value, no ABV to anchor against

    return DealMetrics(
        levered_cash_on_cash=round(coc, 2),
        dscr=round(dscr, 3),
        gross_profit=round(gross_profit, 2),
        notes=[
            f"sweat_equity_pct={sweat_equity_pct:.2f}",
            f"annual_cash_flow={annual_cash_flow:.2f}",
        ],
    )


# ---------------------------------------------------------------------------
# Threshold evaluators (standalone — testable without DealMetrics)
# ---------------------------------------------------------------------------


def evaluate_coc_threshold(coc_pct: float) -> str:
    """Evaluate cash-on-cash return against underwriting thresholds.

    +-----------+-------------------------+
    | CoC Range | Verdict                 |
    +===========+=========================+
    | >= 10%    | ``"strong_go"``         |
    +-----------+-------------------------+
    | >= 5%     | ``"go"``                |
    +-----------+-------------------------+
    | < 5%      | ``"no_go"``             |
    +-----------+-------------------------+

    Args:
        coc_pct: Cash-on-cash return as a percentage (e.g., 10.5 = 10.5%).

    Returns:
        Threshold verdict string.
    """
    if coc_pct >= 10.0:
        return "strong_go"
    if coc_pct >= 5.0:
        return "go"
    return "no_go"


def evaluate_sweat_equity_threshold(se_pct: float) -> str:
    """Evaluate sweat equity percentage against underwriting thresholds.

    +-----------+-------------------------+
    | SE Range  | Verdict                 |
    +===========+=========================+
    | >= 20%    | ``"strong_go"``         |
    +-----------+-------------------------+
    | > 0%      | ``"building_wealth"``   |
    +-----------+-------------------------+
    | <= 0%     | ``"negative"``          |
    +-----------+-------------------------+

    Args:
        se_pct: Sweat equity as a percentage (e.g., 35.0 = 35%).

    Returns:
        Threshold verdict string.
    """
    if se_pct >= 20.0:
        return "strong_go"
    if se_pct > 0.0:
        return "building_wealth"
    return "negative"


# ---------------------------------------------------------------------------
# Composite decision — combines both signals into a single verdict
# ---------------------------------------------------------------------------


def determine_go_no_go(metrics: DealMetrics) -> tuple[str, str, str]:
    """Determine go / no-go from fully-populated DealMetrics.

    Pulls cash-on-cash from ``metrics.levered_cash_on_cash`` and sweat equity
    from the notes field (populated by :func:`calculate_deal_metrics`).

    Args:
        metrics: DealMetrics with computed ``levered_cash_on_cash`` and a
                 ``notes`` entry of the form ``"sweat_equity_pct=45.20"``.

    Returns:
        A 3-tuple of ``(coc_verdict, sweat_equity_verdict, overall_verdict)``
        where:

        * **coc_verdict** — ``"strong_go"`` | ``"go"`` | ``"no_go"``
        * **sweat_equity_verdict** — ``"strong_go"`` | ``"building_wealth"`` | ``"negative"``
        * **overall_verdict** — combined:
          - ``"no_go"`` if either CoC is "no_go" or SE is "negative"
          - ``"strong_go"`` if both CoC and SE are "strong_go"
          - ``"go"`` otherwise
    """
    coc_result = evaluate_coc_threshold(metrics.levered_cash_on_cash)
    se_pct = _extract_sweat_equity_pct(metrics)
    se_result = evaluate_sweat_equity_threshold(se_pct)

    # Combine: either red light → no_go; both green lights → strong_go
    if coc_result == "no_go" or se_result == "negative":
        overall = "no_go"
    elif coc_result == "strong_go" and se_result == "strong_go":
        overall = "strong_go"
    else:
        overall = "go"

    return (coc_result, se_result, overall)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_sweat_equity_pct(metrics: DealMetrics) -> float:
    """Extract sweat-equity percentage from a DealMetrics notes entry.

    Looks for a note starting with ``"sweat_equity_pct="``; returns the float
    value or 0.0 if no such note exists.
    """
    for note in metrics.notes:
        if note.startswith("sweat_equity_pct="):
            try:
                return float(note.split("=", 1)[1])
            except (ValueError, IndexError):
                return 0.0
    return 0.0
