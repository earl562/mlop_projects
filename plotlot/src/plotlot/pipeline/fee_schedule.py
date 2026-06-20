"""Per-jurisdiction itemized development-fee schedules.

The regional cost model (``cost_model.py``) carries a single *coarse aggregate*
impact fee per unit — a deliberately conservative estimate, not a real schedule.
That aggregate is honest as a fallback but it cannot be itemized; when the chat
agent tried to break it into line items it fabricated categories ("police impact
fee $8–18k") that don't exist.

This module is the structured alternative: a registry of **real, itemized,
sourced** fee schedules keyed by ``(state, county)``. When a jurisdiction is
registered, its components (each with an amount + the authority that set it) are
the firm, citable numbers; when it isn't, callers fall back to the coarse
aggregate and must *not* itemize it.

**Generalization:** adding a market is one ``register_fee_schedule`` call / one
registry entry — the wiring in ``entitlement.py`` and the chat payload is market-
agnostic. San Diego is the first target; its real citywide DIF components are the
Mobility, Fire-Rescue, Library (Build Better SD, Resolutions R-314273 / R-314271
/ R-314272) and Parks fees, published in the City's FY fee schedule and scaled by
unit type/size. Amounts are intentionally left to be populated from that official
schedule (dated + sourced) rather than guessed — see ``register_fee_schedule``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeComponent:
    """One itemized development/impact fee that applies per dwelling unit."""

    name: str  # e.g. "Citywide Mobility DIF"
    amount_per_unit: float
    citation: str = ""  # authority that set it, e.g. "Resolution R-314273"
    note: str = ""


@dataclass(frozen=True)
class FeeSchedule:
    """A real, itemized fee schedule for one jurisdiction.

    Provenance (``source``/``effective_date``) is required by the anti-
    hallucination doctrine: an itemized dollar figure is only trustworthy if it
    is traceable to an official, dated schedule.
    """

    jurisdiction: str
    state: str
    components: tuple[FeeComponent, ...] = ()
    source: str = ""  # official source label / URL
    effective_date: str = ""  # ISO date of the schedule edition
    # True when these components cover ALL per-unit development fees, so the total
    # is safe to drive the residual. False for a PARTIAL schedule (e.g. San Diego's
    # city DIFs only — RTCIP, school, and water/sewer capacity fees are separate):
    # the verified line items are still itemized for display, but the residual keeps
    # the conservative coarse all-in so it is never optimistically understated.
    covers_all_fees: bool = True

    @property
    def total_per_unit(self) -> float:
        return sum(c.amount_per_unit for c in self.components)

    @property
    def is_itemized(self) -> bool:
        """True only when it carries real, non-zero components safe to itemize."""
        return bool(self.components) and self.total_per_unit > 0


def _norm_county(county: str) -> str:
    """Lowercase + strip a trailing ' county' (matches cost_model / providers)."""
    c = (county or "").strip().lower()
    return c[: -len(" county")].strip() if c.endswith(" county") else c


# (state_upper, county_normalized) -> FeeSchedule.
#
# Populate from the jurisdiction's OFFICIAL fee schedule (amount + effective
# date + source). Example shape — fill amounts from San Diego's FY fee schedule
# (https://www.sandiego.gov/sites/default/files/feeschedule.pdf) /
# Citywide DIF calculator, do NOT estimate them:
#
#   ("CA", "san diego"): FeeSchedule(
#       jurisdiction="City of San Diego",
#       state="CA",
#       source="City of San Diego FY26 Fee Schedule + Build Better SD DIFs",
#       effective_date="2025-07-01",
#       components=(
#           FeeComponent("Citywide Mobility DIF", <amt>, "Resolution R-314273"),
#           FeeComponent("Citywide Fire-Rescue DIF", <amt>, "Resolution R-314271"),
#           FeeComponent("Citywide Library DIF", <amt>, "Resolution R-314272"),
#           FeeComponent("Parks (Parks for All of Us)", <amt>, "Parks Master Plan"),
#       ),
#   ),
#
# Amounts are the City of San Diego FY2026 Build Better SD Citywide DIFs for a
# MULTI-FAMILY unit in the 951–1,000 sqft band (the representative new-MF size;
# rates scale with unit size across the published table). Verified from the
# official FY26 fee schedule PDF — NOT estimated. This is a PARTIAL schedule
# (covers_all_fees=False): it is the city DIF portion only; RTCIP (SANDAG), school
# (SDUSD), and water/sewer capacity charges are separate and not itemized here.
_FEE_SCHEDULES: dict[tuple[str, str], FeeSchedule] = {
    ("CA", "san diego"): FeeSchedule(
        jurisdiction="City of San Diego",
        state="CA",
        source=(
            "City of San Diego FY2026 Fee Schedule — Build Better SD Citywide DIFs, "
            "Multi-Family, representative ~1,000 sqft unit (rates scale with unit size). "
            "https://www.sandiego.gov/sites/default/files/feeschedule.pdf"
        ),
        effective_date="2025-07-01",
        covers_all_fees=False,  # city DIFs only — RTCIP/school/utility are separate
        components=(
            FeeComponent("Citywide Park DIF", 15438.0, "Build Better SD / Parks for All of Us"),
            FeeComponent("Citywide Fire-Rescue DIF", 943.0, "Resolution R-314271"),
            FeeComponent("Citywide Library DIF", 2394.0, "Resolution R-314272"),
            FeeComponent("Citywide Mobility DIF", 4627.0, "Resolution R-314273"),
        ),
    ),
}


def register_fee_schedule(schedule: FeeSchedule, county: str) -> None:
    """Register (or override) a jurisdiction's itemized fee schedule.

    Lets a deployment load schedules from a data file at startup without editing
    this module.
    """
    _FEE_SCHEDULES[(schedule.state.strip().upper(), _norm_county(county))] = schedule


def get_fee_schedule(state: str, county: str) -> FeeSchedule | None:
    """Return the itemized fee schedule for ``(state, county)``, or None."""
    return _FEE_SCHEDULES.get(((state or "").strip().upper(), _norm_county(county)))
