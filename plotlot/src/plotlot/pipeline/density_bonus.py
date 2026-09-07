"""California state-program density uplift — ADU/JADU, SB9, and Density Bonus.

DETERMINISTIC and ADDITIVE. The base zoning unit count stays the verified, firm
number; this computes the *potential* extra units California statute allows as a
separate, clearly-labeled overlay. Every figure derives from statute constants
cited inline — **no LLM is involved, so there is no hallucination surface**.
Applies to California only; other states return an empty (not-applicable) result.

Programs are reported as distinct pathways, not naively summed: ``max_potential``
is the single best applicable pathway (conservative), and a note flags that a
land-use attorney must confirm eligibility and any stacking.

Statutory basis:
  * ADU / JADU — CA Gov. Code §66310 et seq. (1 ADU + 1 JADU on SFR; up to 2
    detached ADUs on multifamily).
  * SB9 — CA Gov. Code §65852.21 + §66411.7 (SFR urban lot split + duplex →
    up to 4 units).
  * Density Bonus — CA Gov. Code §65915 (developments of 5+ units; up to +50%
    base bonus for an affordable set-aside; AB 1287 can exceed this — we model
    the conservative 50% cap).
"""

from __future__ import annotations

import math

from plotlot.core.types import DensityUplift, UpliftProgram

# Density Bonus Law applies to housing developments of 5 or more units.
_DENSITY_BONUS_MIN_UNITS = 5
# Conservative statutory base cap (pre-AB 1287). AB 1287 (2023) can stack higher.
_MAX_DENSITY_BONUS = 0.50

# Gov. Code §65915 affordability tiers: (min %, bonus at min, max %, bonus at max).
# Bonus is linearly interpolated between the statutory endpoints (AB 2345, 2020).
_DB_TIERS: dict[str, tuple[float, float, float, float]] = {
    "very_low": (5.0, 0.20, 15.0, 0.50),
    "low": (10.0, 0.20, 24.0, 0.50),
    "moderate": (10.0, 0.05, 45.0, 0.50),  # for-sale projects only
}


def _density_bonus_fraction(income_level: str | None, set_aside_pct: float | None) -> float | None:
    """Density bonus fraction for an affordability election, or None if ineligible."""
    if income_level is None or set_aside_pct is None:
        return None
    tier = _DB_TIERS.get(income_level)
    if tier is None:
        return None
    lo_pct, lo_bonus, hi_pct, hi_bonus = tier
    if set_aside_pct < lo_pct:
        return None
    if set_aside_pct >= hi_pct:
        return hi_bonus
    slope = (hi_bonus - lo_bonus) / (hi_pct - lo_pct)
    return lo_bonus + slope * (set_aside_pct - lo_pct)


def compute_density_uplift(
    base_units: int,
    *,
    state: str,
    property_type: str = "",
    set_aside_pct: float | None = None,
    income_level: str | None = None,
    base_is_provisional: bool = False,
    in_flood_hazard: bool = False,
    has_wetlands: bool = False,
) -> DensityUplift:
    """Compute the additive California density-uplift overlay.

    Args:
        base_units: Verified base-zoning max units (the firm number).
        state: Two-letter state code; programs apply only when "CA".
        property_type: Optional hint ("single_family", "multifamily", …).
        set_aside_pct / income_level: Optional Density Bonus affordability
            election; when omitted the statutory max (+50%) is reported.
        base_is_provisional: True if the base unit count was not source-verified.
        in_flood_hazard: Parcel is in a FEMA Special Flood Hazard Area (from
            ``site_risk``) — triggers the SB9 site-exclusion restriction.
        has_wetlands: Parcel intersects mapped wetlands — same SB9 restriction.

    Returns:
        DensityUplift with one UpliftProgram per applicable pathway. Programs the
        parcel is statutorily restricted from (e.g. SB9 in a flood zone) are
        marked ``eligibility="restricted"`` and excluded from ``max_potential``.
    """
    result = DensityUplift(base_units=base_units, state=(state or "").upper())

    if result.state != "CA":
        result.notes.append("State density programs are modeled for California only.")
        return result
    if base_units <= 0:
        result.notes.append("No base unit count — cannot compute density uplift.")
        return result

    is_sfr = base_units == 1 or property_type == "single_family"
    programs: list[UpliftProgram] = []

    # ── ADU / JADU — Gov. Code §66310 et seq. ──
    if is_sfr:
        programs.append(
            UpliftProgram(
                name="ADU + JADU",
                statute="CA Gov. Code §66310 et seq.",
                additional_units=2,
                potential_units=base_units + 2,
                basis="Single-family lot: 1 ADU + 1 JADU permitted ministerially.",
                requirements="Ministerial approval; size/setback limits apply.",
            )
        )
    else:
        programs.append(
            UpliftProgram(
                name="ADU (detached)",
                statute="CA Gov. Code §66310 et seq.",
                additional_units=2,
                potential_units=base_units + 2,
                basis="Multifamily lot: up to 2 detached ADUs (conversion ADUs may add more).",
                requirements="Ministerial approval; conversion ADUs require existing structure.",
            )
        )

    # ── SB9 — Gov. Code §65852.21 / §66411.7 (single-family lots only) ──
    if is_sfr:
        # Deterministic eligibility check against the site hazards we already
        # compute. SB9 incorporates the §65913.4 site exclusions (flood/wetlands
        # among them), so a hazard parcel is restricted, not firm upside.
        hazards: list[str] = []
        if in_flood_hazard:
            hazards.append("a FEMA Special Flood Hazard Area")
        if has_wetlands:
            hazards.append("mapped wetlands")
        sb9_requirements = (
            "Urban-infill SFR lot; owner-occupancy for the lot split; excludes "
            "high fire/flood/historic/coastal-hazard parcels."
        )
        sb9_eligibility = "eligible"
        if hazards:
            sb9_eligibility = "restricted"
            sb9_requirements = (
                f"RESTRICTED — parcel intersects {' and '.join(hazards)}; SB9 site "
                f"exclusions (§66411.7) apply unless FEMA/site requirements are met. "
                + sb9_requirements
            )
        programs.append(
            UpliftProgram(
                name="SB9 lot split + duplex",
                statute="CA Gov. Code §65852.21 / §66411.7",
                eligibility=sb9_eligibility,
                additional_units=4 - base_units,
                potential_units=4,
                basis="SFR urban lot split into 2 lots × up to 2 units each = up to 4 units.",
                requirements=sb9_requirements,
            )
        )

    # ── Density Bonus — Gov. Code §65915 (developments of 5+ units) ──
    if base_units >= _DENSITY_BONUS_MIN_UNITS:
        frac = _density_bonus_fraction(income_level, set_aside_pct)
        if frac is None:
            if income_level is None and set_aside_pct is None:
                frac = _MAX_DENSITY_BONUS
                requirements = (
                    "Up to +50% — e.g. 15% very-low-income or 24% low-income affordable "
                    "set-aside (Gov. Code §65915)."
                )
            else:
                frac = 0.0
                requirements = (
                    f"Set-aside {set_aside_pct:g}% is below {income_level or 'the'} income "
                    "threshold — not eligible for Density Bonus."
                )
        else:
            requirements = (
                f"{set_aside_pct:g}% {(income_level or '').replace('_', '-')}-income "
                "affordable set-aside."
            )
        bonus_units = math.floor(base_units * frac)
        programs.append(
            UpliftProgram(
                name="Density Bonus",
                statute="CA Gov. Code §65915",
                additional_units=bonus_units,
                potential_units=base_units + bonus_units,
                basis=f"+{frac * 100:.0f}% density bonus on {base_units} base units.",
                requirements=requirements,
            )
        )

    result.programs = programs
    # Only eligible pathways drive the headline upside — a restricted program
    # (e.g. SB9 in a flood zone) must not inflate the "up to N units" figure.
    eligible = [p for p in programs if p.eligibility == "eligible"]
    result.max_potential_units = max((p.potential_units for p in eligible), default=base_units)

    if any(p.eligibility != "eligible" for p in programs):
        result.notes.append(
            "One or more programs are restricted by site hazards (see requirements)."
        )
    if base_is_provisional:
        result.notes.append(
            "Base unit count is provisional — the uplift potential inherits that uncertainty."
        )
    result.notes.append(
        "Potential is additive to base zoning and reported per program (not stacked). "
        "Confirm eligibility and any program stacking with a land-use attorney."
    )
    return result
