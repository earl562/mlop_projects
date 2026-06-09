"""Deal evaluator — full property analysis for land acquisition.

Evaluates each vacant lot against the acquisition criteria:
1. Zoning compliance + max unit potential (hidden gem detection)
2. Utility availability assessment
3. Environmental externalities
4. Comparable sales analysis (land + new construction)
5. Offer price calculation using the NC formula

Per user's sales script:
- "Formula: New construction sale x .15% - 15K assignment = Our Offer"
- Questions: survey, water/sewer, perc test, virgin land, dump site, easements, flood zone, deed restrictions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from plotlot.harness.interpreter_skills import ComplianceResult
from plotlot.harness.extended_skills import check_environmental, EnvironmentalInputs


# ==========================================================================
# Offer formula per user's NC script
# ==========================================================================

def calculate_offer(new_construction_sale_price: float, assignment_fee: float = 15000, margin_pct: float = 0.15) -> float:
    """NC land offer formula.

    Per user's script: "New construction sale x 15% - 15K assignment = Our Offer"
    The 15% margin accounts for construction costs, soft costs, and profit.
    Minimum offer: $1,000 (any lower is not worth pursuing).
    """
    offer = new_construction_sale_price * margin_pct - assignment_fee
    return max(1000.0, offer)


# ==========================================================================
# Max unit potential (hidden gem detection)
# ==========================================================================

def estimate_max_units(lot_size_sqft: float, zone_density_per_acre: float = 4, min_lot_per_unit_sqft: float = 5000) -> int:
    """Estimate maximum buildable units on a lot.

    Hidden gem detection: a lot zoned for single-family might support 2-4 units
    if the lot is large enough and zoning allows multi-family by right.
    """
    acres = lot_size_sqft / 43560.0
    by_density = int(acres * zone_density_per_acre)
    by_min_lot = int(lot_size_sqft / min_lot_per_unit_sqft) if min_lot_per_unit_sqft > 0 else 999
    return max(1, min(by_density, by_min_lot))


# ==========================================================================
# Deal scoring
# ==========================================================================

def score_deal(
    lot_acres: float,
    assessed_value: float,
    est_value: float,
    last_sale_amount: float,
    max_units: int,
    zoning_compliant: bool,
    utilities: bool,
    environmental_flags: int,
    owner_occupied: bool,
    mls_failed: bool,
) -> int:
    """Score a deal 0-10 based on acquisition criteria.

    Scoring:
    - Large lot (>0.5 acre): +2
    - Value gap (assessed < 50% est): +2
    - Multi-unit potential (2+ units): +2
    - Zoning compliant: +1
    - Utilities: +1
    - No environmental flags: +1
    - MLS previously failed (motivated seller): +1
    - Non-owner-occupied (less emotional): +1
    - Low last sale (paid less than assessed): +1
    """
    score = 0
    if lot_acres >= 0.5:
        score += 2
    elif lot_acres >= 0.25:
        score += 1
    if assessed_value > 0 and est_value > 0 and assessed_value < est_value * 0.5:
        score += 2
    if max_units >= 3:
        score += 2
    elif max_units >= 2:
        score += 1
    if zoning_compliant:
        score += 1
    if utilities:
        score += 1
    if environmental_flags == 0:
        score += 1
    if mls_failed:
        score += 1
    if not owner_occupied:
        score += 1
    if last_sale_amount > 0 and assessed_value > 0 and last_sale_amount < assessed_value:
        score += 1
    return min(10, score)


# ==========================================================================
# Sales script questions (user's Step 3)
# ==========================================================================

SALES_SCRIPT_QUESTIONS = [
    "What is the full address or Parcel number?",
    "What is the acreage of the lot?",
    "Has the lot been surveyed, if so when? And do you have access to that survey to share with us?",
    "Are City Sewer & Water taps already in place? Or does it just have access to Water & Sewer?",
    "If no city sewer & Water, has the land ever been perc tested? And do you have the results of that test?",
    "Did a house ever sit on this lot or is the land virgin?",
    "Was this a previous dump site at any point?",
    "Are there any known easements?",
    "Are there any deed restrictions?",
    "Is there a flood zone or floodplain?",
]

FIRST_HOLD_MESSAGE = "First hold — going back to the underwriters to see if they approved this lot."
SECOND_HOLD_MESSAGE = "Second hold — coming back with our offer on the lot."

OFFER_FORMULA_EXPLANATION = "Our offer: (New construction sale × 15%) - $15,000 assignment = Our Offer. Minimum $1,000."



def generate_sales_script(lead_name: str, property_address: str, lot_acres: float) -> str:
    """Generate the full sales outreach script for a lead."""
    questions = "\n".join(f"- {q}" for q in SALES_SCRIPT_QUESTIONS[:4])
    follow_up = "\n".join(f"- {q}" for q in SALES_SCRIPT_QUESTIONS[4:8])
    close = "\n".join(f"- {q}" for q in SALES_SCRIPT_QUESTIONS[8:])
    return f"""OUTREACH SCRIPT — {lead_name} — {property_address}
Lot size: {lot_acres:.1f} acres

INITIAL CONTACT:
{questions}

AFTER PROPERTY DETAILS:
{follow_up}

FIRST HOLD:
{FIRST_HOLD_MESSAGE}

RETURN FROM HOLD:
{close}

SECOND HOLD:
{SECOND_HOLD_MESSAGE}

OFFER:
{OFFER_FORMULA_EXPLANATION}

If asking price is significantly lower than our offer, lock them up between $5K-$15K under asking.
"""


# ==========================================================================
# Due diligence checklist per user's document
# ==========================================================================

DUE_DILIGENCE_CHECKLIST = {
    "zoning": ["Verify existing zoning", "Check compliance for intended use", "Verify frontage requirements", "Verify square footage minimums", "Check front/side/rear setbacks"],
    "utilities": ["City water or sewer taps in place", "Water/sewer taps available and cost", "Septic and well — allowed?", "Septic and well — will land perk?", "Electric availability nearby", "Natural gas availability"],
    "buildability": ["Easements check", "Deed restrictions (override zoning)", "Flood zone or floodplain", "Previous dump site", "Virgin land vs previous house", "Topography — flat vs sloped"],
    "comps": ["Land comps within 1-3 mile radius (max 5)", "New build comps within last 6-12 months", "What they bought land for and sold house for", "Visit comps in person", "Develop build strategy based on comps"],
}
