"""The composite trust gate for a by-right unit count.

A unit count is only as trustworthy as its **inputs**, not just the ordinance rule
it applied. Three inputs can each independently make a count unfirm:

* the **lot area** — an assessor's recorded legal lot, or a GIS polygon estimate
  that once read 6,471 against the assessor's 7,710 and flipped 7 units to 6;
* the **zoning district** — read off a parcel/zoning GIS layer, or absent (in
  which case every dimensional standard behind the count was retrieved without a
  confirmed district);
* the **buildable area** — density is applied to GROSS lot area, which silently
  assumes the whole lot is developable. True in flat Florida, false on a San Diego
  hillside where steep ground is deducted first.

**Why this module exists.** This verdict used to be computed inline in
``api/chat.py``, which meant only the chat and harness transports applied it. The
SSE ``/analyze`` route — what the web UI consumes — derived its own weaker flag
from ``extraction_verification.offer_is_provisional`` alone, so the very same
parcel was PROVISIONAL in chat and firm in the browser. A trust gate that depends
on which door the caller came through is not a trust gate. Compute it here; every
transport reads the same answer.

**Deliberate non-goals.**

* An *unmeasured* slope does not make a count provisional. Terrain is best-effort
  (3DEP can fail, and the SSE path does not measure it at all), and treating
  "unknown" as "constrained" would flag most reports for no evidential reason.
  It is reported honestly as unmeasured rather than quietly as confirmed.
* This module does not *suppress* a count. Whether an undetermined district should
  zero out the number is a separate product decision; this is the gate the decision
  would be built on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from plotlot.core.types import ZoningReport


@dataclass(frozen=True)
class ByRightTrust:
    """Whether a by-right unit count may be presented as firm, and why not.

    **Positive confirmation and known-bad are deliberately different facts**, and
    conflating them is a real bug this type is shaped to prevent. A Florida county
    that simply does not publish lot provenance leaves ``lot_size_source`` empty:
    that is *unknown*, and unknown must not downgrade a count the way a *known*
    polygon estimate does. So each input carries a "confirmed" flag for reporting
    and, where they differ, a separate flag for gating.
    """

    #: Reporting: district was read from a parcel/zoning GIS layer.
    zoning_confirmed: bool = False
    #: Gating: a district exists at all. Absent -> every standard below it is unmoored.
    zoning_determined: bool = False
    #: Reporting: lot area is the county assessor's recorded legal lot.
    lot_confirmed: bool = False
    #: Gating: lot area is known to be a GIS polygon estimate (not merely unknown).
    lot_estimated: bool = False
    #: Slope was actually measured for this parcel (3DEP returned a result).
    slope_measured: bool = False
    #: Gating: measured AND steep enough that gross lot area is no longer a safe proxy.
    slope_constrained: bool = False
    #: Gating: the extraction verifier could not confirm the rule itself.
    extraction_provisional: bool = False
    #: Deterministic, user-facing explanations — echo these, never re-compose them.
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def buildable_area_confirmed(self) -> bool:
        """True only when slope was measured *and* came back unconstrained.

        Not-measured is reported as not-confirmed. The alternative — defaulting an
        unmeasured parcel to ``True`` — asserts a fact nobody checked, which is the
        exact shape of error this codebase exists to avoid. Note this is a
        *reporting* flag only: an unmeasured slope does not gate ``is_provisional``.
        """
        return self.slope_measured and not self.slope_constrained

    @property
    def is_provisional(self) -> bool:
        return bool(
            self.extraction_provisional
            or self.lot_estimated
            or not self.zoning_determined
            or self.slope_constrained
        )

    @property
    def verification(self) -> str:
        return "provisional" if self.is_provisional else "verified"


def assess_by_right_trust(report: ZoningReport) -> ByRightTrust:
    """Derive the composite trust verdict for ``report``'s by-right count.

    Pure and cheap — call it at render time in each transport rather than caching
    it on the report, because terrain and property data are populated by
    augmentation steps that finish at different points in different pipelines.
    """
    pr = report.property_record
    lot_source = (pr.lot_size_source if pr else "") or ""
    terrain = report.terrain
    ev = report.extraction_verification

    zoning_confirmed = (report.zoning_source or "") == "gis"
    zoning_determined = bool(report.zoning_district)
    lot_confirmed = lot_source == "assessor"
    lot_estimated = lot_source == "geometry"
    slope_measured = terrain is not None
    slope_constrained = bool(terrain and terrain.slope_constrained)
    extraction_provisional = bool(ev and ev.offer_is_provisional)

    # Only the GATING conditions produce a reason. An unknown-provenance lot or an
    # unmeasured slope is a gap in what we know, not a defect in the count, and
    # listing it here would tell the user a firm number is shaky.
    reasons: list[str] = []
    if not zoning_determined:
        reasons.append(
            "the zoning district was NOT read from a GIS layer, so every dimensional "
            "standard behind this count is unconfirmed"
        )
    if lot_estimated:
        reasons.append(
            "the lot area is a GIS polygon estimate rather than the assessor's recorded legal lot"
        )
    if slope_constrained:
        reasons.append(
            "density was applied to GROSS lot area on sloped ground, so this is an "
            "UPPER BOUND, not an achievable yield"
        )
    if extraction_provisional:
        reasons.append("automated source-verification of the ordinance rule was inconclusive")

    return ByRightTrust(
        zoning_confirmed=zoning_confirmed,
        zoning_determined=zoning_determined,
        lot_confirmed=lot_confirmed,
        lot_estimated=lot_estimated,
        slope_measured=slope_measured,
        slope_constrained=slope_constrained,
        extraction_provisional=extraction_provisional,
        reasons=tuple(reasons),
    )
