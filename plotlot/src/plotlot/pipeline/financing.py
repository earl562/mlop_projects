"""Real estate financing calculations — amortization, DSCR, interest carry, capital stack.

Pure deterministic functions for the underwriting pipeline. Computes monthly
loan payments via standard amortization, reverse-engineers maximum loan amount
from a DSCR constraint, carries construction-period interest, and assembles
a full capital stack (senior debt + equity) from project costs and loan terms.
"""

from __future__ import annotations

import logging

from plotlot.core.types import CapitalStack, FinancingTerms

logger = logging.getLogger(__name__)

# Default assumed equity return for WACC when no mezz/preferred equity is present.
_DEFAULT_EQUITY_RETURN_PCT = 15.0


# ---------------------------------------------------------------------------
# Amortization
# ---------------------------------------------------------------------------


def calculate_monthly_payment(
    principal: float,
    annual_rate_pct: float,
    term_years: int,
) -> float:
    """Compute the fully-amortizing monthly payment.

    Uses the standard amortization formula:

        M = P * [r(1+r)^n] / [(1+r)^n - 1]

    where:
        P = principal
        r = monthly interest rate (annual_rate_pct / 100 / 12)
        n = total number of payments (term_years * 12)

    Args:
        principal: Loan amount in dollars.
        annual_rate_pct: Annual interest rate as a percentage (e.g., 7.25).
        term_years: Loan term in years (e.g., 30).

    Returns:
        Monthly payment in dollars. Returns 0.0 when principal ≤ 0,
        rate ≤ 0, or term ≤ 0.
    """
    if principal <= 0 or annual_rate_pct <= 0 or term_years <= 0:
        return 0.0

    r = annual_rate_pct / 100.0 / 12.0
    n = term_years * 12

    if r == 0:
        return principal / n

    factor = (1 + r) ** n
    return principal * (r * factor) / (factor - 1)


# ---------------------------------------------------------------------------
# DSCR — max loan constrained by debt service coverage
# ---------------------------------------------------------------------------


def calculate_max_loan_from_dscr(
    monthly_noi: float,
    dscr_target: float,
    annual_rate_pct: float,
    term_years: int,
) -> float:
    """Compute the maximum loan amount a property can support given a DSCR floor.

    DSCR = NOI / Debt Service, so:

        max_monthly_debt_service = monthly_noi / dscr_target

    Then reverse the amortization formula to solve for principal:

        P = M * [(1+r)^n - 1] / [r(1+r)^n]

    where M = max_monthly_debt_service.

    Args:
        monthly_noi: Stabilized monthly net operating income.
        dscr_target: Minimum DSCR required by the lender (e.g., 1.25).
        annual_rate_pct: Annual interest rate as a percentage (e.g., 7.25).
        term_years: Amortization term in years (e.g., 30).

    Returns:
        Maximum loan amount in dollars. Returns 0.0 when inputs are
        non-positive.
    """
    if monthly_noi <= 0 or dscr_target <= 0 or annual_rate_pct <= 0 or term_years <= 0:
        return 0.0

    max_monthly_payment = monthly_noi / dscr_target

    r = annual_rate_pct / 100.0 / 12.0
    n = term_years * 12

    if r == 0:
        return max_monthly_payment * n

    factor = (1 + r) ** n
    return max_monthly_payment * (factor - 1) / (r * factor)


# ---------------------------------------------------------------------------
# Interest carry (construction / bridge period)
# ---------------------------------------------------------------------------


def calculate_interest_carry(
    loan_amount: float,
    annual_rate_pct: float,
    term_months: int,
) -> float:
    """Compute simple interest accrued over a construction or carry period.

    Assumes interest-only during the carry period (no principal amortization).
    This is the standard treatment for construction loans.

        interest = loan_amount * (annual_rate_pct / 100) * (term_months / 12)

    Args:
        loan_amount: Outstanding loan balance during the carry period.
        annual_rate_pct: Annual interest rate as a percentage (e.g., 9.0).
        term_months: Length of the carry period in months.

    Returns:
        Total interest cost in dollars. Returns 0.0 when any input is ≤ 0.
    """
    if loan_amount <= 0 or annual_rate_pct <= 0 or term_months <= 0:
        return 0.0

    return loan_amount * (annual_rate_pct / 100.0) * (term_months / 12.0)


# ---------------------------------------------------------------------------
# Capital stack
# ---------------------------------------------------------------------------


def calculate_capital_stack(
    land_cost: float,
    hard_costs: float,
    soft_costs: float,
    monthly_noi: float,
    financing_terms: FinancingTerms,
) -> CapitalStack:
    """Assemble the full capital structure for a development deal.

    Computes senior debt as the minimum of the LTC constraint and the DSCR
    constraint, then backs into required sponsor equity. Produces a
    ``CapitalStack`` with percentage weightings and a blended WACC.

    The DSCR constraint uses ``financing_terms.min_dscr``, ``interest_rate``,
    and ``amortization_years``. The LTC constraint uses ``financing_terms.loan_to_cost``.

    Args:
        land_cost: Land acquisition price (dollars).
        hard_costs: Total hard construction costs (dollars).
        soft_costs: Architectural, legal, permitting, and financing soft costs (dollars).
        monthly_noi: Stabilized monthly net operating income (dollars).
        financing_terms: ``FinancingTerms`` describing the senior loan.

    Returns:
        A fully-populated ``CapitalStack``.
    """
    total_project_cost = land_cost + hard_costs + soft_costs

    # ---- senior debt ----
    # LTC (loan-to-cost) ceiling
    max_senior_from_ltc: float = 0.0
    if financing_terms.loan_to_cost > 0:
        max_senior_from_ltc = total_project_cost * (financing_terms.loan_to_cost / 100.0)

    # DSCR ceiling
    max_senior_from_dscr = calculate_max_loan_from_dscr(
        monthly_noi=monthly_noi,
        dscr_target=financing_terms.min_dscr,
        annual_rate_pct=financing_terms.interest_rate,
        term_years=financing_terms.amortization_years,
    )

    # Take the tighter of the two constraints
    candidates = [v for v in (max_senior_from_ltc, max_senior_from_dscr) if v > 0]
    senior_debt = min(candidates) if candidates else 0.0

    senior_debt_pct = (
        (senior_debt / total_project_cost) * 100.0 if total_project_cost > 0 else 0.0
    )

    # ---- subordinate tranches ----
    # v1: mezzanine and preferred equity are not computed from a single
    # FinancingTerms input.  Future iterations can layer in mezz_terms.
    mezzanine_debt = 0.0
    mezzanine_debt_pct = 0.0
    preferred_equity = 0.0
    preferred_equity_pct = 0.0

    # ---- sponsor equity ----
    sponsor_equity = total_project_cost - senior_debt - mezzanine_debt - preferred_equity
    sponsor_equity_pct = (
        (sponsor_equity / total_project_cost) * 100.0 if total_project_cost > 0 else 0.0
    )

    # ---- weighted cost of capital ----
    weighted_cost_of_debt: float = 0.0
    if senior_debt > 0 and financing_terms.interest_rate > 0:
        weighted_cost_of_debt = (senior_debt_pct / 100.0) * financing_terms.interest_rate

    weighted_cost_of_equity: float = 0.0
    if sponsor_equity > 0:
        weighted_cost_of_equity = (sponsor_equity_pct / 100.0) * _DEFAULT_EQUITY_RETURN_PCT

    wacc = weighted_cost_of_debt + weighted_cost_of_equity

    # ---- notes ----
    notes: list[str] = []
    if senior_debt <= 0 and total_project_cost > 0:
        notes.append(
            "No senior debt could be sized — check NOI, DSCR target, or LTC inputs."
        )
    if max_senior_from_dscr > 0 and max_senior_from_ltc > 0:
        binding = "DSCR" if max_senior_from_dscr < max_senior_from_ltc else "LTC"
        notes.append(f"Senior debt constrained by {binding}")
    if sponsor_equity < 0:
        notes.append(
            f"Sponsor equity is negative (${sponsor_equity:,.0f}) — "
            "total project cost exceeds available debt capacity."
        )

    return CapitalStack(
        total_project_cost=total_project_cost,
        senior_debt=senior_debt,
        senior_debt_pct=senior_debt_pct,
        mezzanine_debt=mezzanine_debt,
        mezzanine_debt_pct=mezzanine_debt_pct,
        preferred_equity=preferred_equity,
        preferred_equity_pct=preferred_equity_pct,
        sponsor_equity=sponsor_equity,
        sponsor_equity_pct=sponsor_equity_pct,
        weighted_cost_of_debt=weighted_cost_of_debt,
        weighted_cost_of_equity=weighted_cost_of_equity,
        weighted_avg_cost_of_capital=wacc,
        senior_terms=financing_terms,
        mezz_terms=None,
        notes=notes,
    )
