"""Residential infill scenario analyzer (the real product use case).

Given a real South FL address, identify the zoning district (OpenData/ArcGIS),
pull the dimensional standard (Municode verified-fact fast path), and run
MULTIPLE development scenarios per lot — by-right density, lot-split feasibility,
missing-middle/ADU eligibility — each as a typed Claim (kind=hypothesis for
speculative upside, kind=calculation for deterministic by-right numbers).

This is the Kleyman methodology applied to the infill use case: every scenario
is evidenced (source_url + origin), speculative upside is a hypothesis with a
next_verification_step, never presented as guaranteed (spec acceptance #6).

Scenario taxonomy (each produces a Claim):
  * by_right_density      — calculate_max_units on the lot + district standard.
                            kind=calculation (deterministic from inputs).
  * lot_split_feasibility — can the lot be split into N conforming lots?
                            kind=hypothesis (entitlement upside, needs planner).
  * missing_middle_adu    — ADU / duplex / triplex eligibility under the zone.
                            kind=hypothesis (needs ordinance use-table check).
  * assemblage_potential  — adjacent parcel assemblage for higher density.
                            kind=hypothesis (needs ownership + adjacency check).

Scenarios that can't be determined from current data emit a hypothesis with a
concrete next_verification_step (never fabricated).
"""

from __future__ import annotations

from dataclasses import dataclass

from plotlot.domain.claims import Claim, ClaimKind, ClaimOrigin
from plotlot.pipeline.calculator import calculate_max_units
from plotlot.storage.dimensional_standards import get_dimensional_standard


@dataclass
class InfillScenarioResult:
    """One scenario run against a real infill lot."""

    scenario: (
        str  # by_right_density | lot_split_feasibility | missing_middle_adu | assemblage_potential
    )
    claim: Claim
    summary: str
    feasible: bool | None = None  # None = needs further verification


async def analyze_residential_infill(
    *,
    address: str,
    municipality: str,
    district_code: str,
    lot_size_sqft: float,
    lot_width_ft: float | None = None,
    lot_depth_ft: float | None = None,
    source_url: str = "",
    allow_fixture_fallback: bool = True,
) -> list[InfillScenarioResult]:
    """Run multiple development scenarios against a real infill lot.

    Args mirror what lookup_address produces: the address, the zoning district
    label (from OpenData), the parcel facts (lot size/width/depth), and the
    source_url of the OpenData zoning query (for provenance).

    Returns one InfillScenarioResult per scenario. Each carries a typed Claim
    with the right kind (calculation for deterministic, hypothesis for
    speculative) and provenance (origin + source_url).
    """
    results: list[InfillScenarioResult] = []
    standard = await get_dimensional_standard(
        municipality, district_code, allow_fixture_fallback=allow_fixture_fallback
    )

    # Scenario 1: by-right density (the deterministic Kleyman step).
    results.append(
        _by_right_density(
            address=address,
            municipality=municipality,
            district_code=district_code,
            lot_size_sqft=lot_size_sqft,
            lot_width_ft=lot_width_ft,
            lot_depth_ft=lot_depth_ft,
            standard=standard,
            source_url=source_url,
        )
    )

    # Scenario 2: lot-split feasibility (speculative — hypothesis).
    results.append(
        _lot_split_feasibility(
            address=address,
            municipality=municipality,
            district_code=district_code,
            lot_size_sqft=lot_size_sqft,
            lot_width_ft=lot_width_ft,
            standard=standard,
            source_url=source_url,
        )
    )

    # Scenario 3: missing-middle / ADU eligibility (speculative — hypothesis).
    results.append(
        _missing_middle_adu(
            address=address,
            municipality=municipality,
            district_code=district_code,
            standard=standard,
            source_url=source_url,
        )
    )

    # Scenario 4: assemblage potential (speculative — hypothesis).
    results.append(
        _assemblage_potential(
            address=address,
            municipality=municipality,
            district_code=district_code,
            lot_size_sqft=lot_size_sqft,
            source_url=source_url,
        )
    )

    return results


def _by_right_density(
    *,
    address,
    municipality,
    district_code,
    lot_size_sqft,
    lot_width_ft,
    lot_depth_ft,
    standard,
    source_url,
) -> InfillScenarioResult:
    """Scenario 1: by-right max units (deterministic calculation)."""
    provenance_url = (standard.source_url if standard else "") or source_url
    if standard is None:
        # No verified standard — can't compute by-right deterministically.
        return InfillScenarioResult(
            scenario="by_right_density",
            claim=Claim(
                field_key="hypothesis.by_right_density",
                value=None,
                kind=ClaimKind.HYPOTHESIS,
                origin=ClaimOrigin.UNKNOWN,
                confidence=0.3,
                source_url=source_url,
                next_verification_step=(
                    f"Ingest the {district_code} dimensional standard for "
                    f"{municipality} from the ordinance corpus (no verified row)."
                ),
                metadata={"address": address, "district_code": district_code},
            ),
            summary=f"No verified dimensional standard for {municipality}/{district_code} — by-right density undetermined.",
            feasible=None,
        )

    analysis = calculate_max_units(
        lot_size_sqft=lot_size_sqft,
        params=standard,
        lot_width_ft=lot_width_ft,
        lot_depth_ft=lot_depth_ft,
    )
    return InfillScenarioResult(
        scenario="by_right_density",
        claim=Claim(
            field_key="calculation.by_right_max_units",
            value=analysis.max_units,
            kind=ClaimKind.CALCULATION,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            source_url=provenance_url,
            metadata={
                "address": address,
                "district_code": district_code,
                "governing_constraint": analysis.governing_constraint,
                "origin": analysis.origin,
            },
        ),
        summary=(
            f"By-right: {analysis.max_units} units ({analysis.governing_constraint}) "
            f"under {district_code} in {municipality}. Origin: {analysis.origin}."
        ),
        feasible=analysis.max_units > 0,
    )


def _lot_split_feasibility(
    *,
    address,
    municipality,
    district_code,
    lot_size_sqft,
    lot_width_ft,
    standard,
    source_url,
) -> InfillScenarioResult:
    """Scenario 2: lot-split feasibility (speculative — hypothesis).

    A lot can be split if it has enough area + width to create N conforming
    lots meeting the district's min lot area / min lot width. This is a
    preliminary screen — actual feasibility needs the planner + subdivision regs.
    """
    if standard and standard.min_lot_area_sqft and lot_size_sqft:
        min_lot = standard.min_lot_area_sqft
        potential_lots = int(lot_size_sqft // min_lot)
        min_width_ok = (
            standard.min_lot_width_ft and lot_width_ft and lot_width_ft >= standard.min_lot_width_ft
        ) or lot_width_ft is None
        feasible = potential_lots >= 2 and min_width_ok
        summary = (
            f"Lot-split screen: {lot_size_sqft:,.0f} sqft ÷ {min_lot:,.0f} min = "
            f"{potential_lots} potential lots; min width "
            f"{standard.min_lot_width_ft}ft {'OK' if min_width_ok else 'INSUFFICIENT'}."
        )
        next_step = (
            "Confirm with municipal planner: subdivision regs, frontage requirements, "
            "and platting process. Screen is preliminary, not entitlement approval."
        )
    else:
        potential_lots = None
        feasible = None
        summary = "Lot-split undetermined — no verified min-lot-area standard."
        next_step = (
            f"Ingest {district_code} dimensional standard for {municipality} "
            f"(min_lot_area_sqft missing)."
        )

    return InfillScenarioResult(
        scenario="lot_split_feasibility",
        claim=Claim(
            field_key="hypothesis.lot_split",
            value={"potential_lots": potential_lots, "feasible": feasible},
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.LOCAL_AUTHORITY if standard else ClaimOrigin.UNKNOWN,
            confidence=0.35,  # speculative screen, not approval
            source_url=(standard.source_url if standard else "") or source_url,
            next_verification_step=next_step,
            metadata={"address": address, "district_code": district_code},
        ),
        summary=summary,
        feasible=feasible,
    )


def _missing_middle_adu(
    *,
    address,
    municipality,
    district_code,
    standard,
    source_url,
) -> InfillScenarioResult:
    """Scenario 3: missing-middle / ADU eligibility (speculative — hypothesis).

    Screen whether the district likely permits ADUs / duplexes / triplexes based
    on density. RS-* single-family districts typically allow ADUs; RM-* allow
    duplexes/triplexes by-right. Actual eligibility needs the use-table check.
    """
    density = standard.max_density_units_per_acre if standard else None
    is_single_family = district_code.upper().startswith(("RS", "R-1", "R-2"))
    if is_single_family:
        eligible_for = "ADU (accessory dwelling unit)"
        next_step = "Confirm ADU ordinance for {} (max size, height, owner-occupancy).".format(
            municipality
        )
    elif density and density >= 8:
        eligible_for = "duplex/triplex (missing-middle)"
        next_step = "Confirm use table permits multifamily in {} {}.".format(
            municipality, district_code
        )
    else:
        eligible_for = "uncertain"
        next_step = "Check use regulations for {} {}.".format(municipality, district_code)

    return InfillScenarioResult(
        scenario="missing_middle_adu",
        claim=Claim(
            field_key="hypothesis.missing_middle_adu",
            value={"eligible_for": eligible_for},
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.LOCAL_AUTHORITY if standard else ClaimOrigin.UNKNOWN,
            confidence=0.3,
            source_url=(standard.source_url if standard else "") or source_url,
            next_verification_step=next_step,
            metadata={"address": address, "district_code": district_code, "density": density},
        ),
        summary=f"Missing-middle screen: {eligible_for}. Needs use-table confirmation.",
        feasible=None,
    )


def _assemblage_potential(
    *,
    address,
    municipality,
    district_code,
    lot_size_sqft,
    source_url,
) -> InfillScenarioResult:
    """Scenario 4: assemblage potential (speculative — hypothesis).

    Larger lots in higher-density districts have assemblage potential for
    multifamily/commercial. Screen is rough; actual needs ownership + adjacency.
    """
    return InfillScenarioResult(
        scenario="assemblage_potential",
        claim=Claim(
            field_key="hypothesis.assemblage",
            value={"lot_size_sqft": lot_size_sqft},
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.UNKNOWN,
            confidence=0.2,
            source_url=source_url,
            next_verification_step=(
                "Pull adjacent parcel ownership + lot sizes from the county "
                "property appraiser; check if contiguous parcels can combine "
                f"for higher density under {district_code}."
            ),
            metadata={"address": address, "district_code": district_code},
        ),
        summary="Assemblage screen: needs adjacent ownership + lot-size pull.",
        feasible=None,
    )
