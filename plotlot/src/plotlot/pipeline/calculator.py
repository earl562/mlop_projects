"""Deterministic max-allowable-units calculator.

Pure functions — no I/O. Takes lot dimensions + NumericZoningParams,
returns DensityAnalysis with constraint breakdown.

The governing constraint is whichever yields the fewest units.
"""

import math
import re

from plotlot.core.types import ConstraintResult, DensityAnalysis, NumericZoningParams
from plotlot.domain.dimensional_standard import DistrictDimensionalStandard
from plotlot.observability.tracing import trace

SQFT_PER_ACRE = 43_560

# Default residential floor-to-floor height (ft) used to translate a height limit
# into a story count. Deliberately conservative — taller assumed stories yield
# *fewer* stories and thus fewer units, the safe direction for a max-offer tool.
# Real story heights vary, so any height-derived story count is surfaced as a note.
RESIDENTIAL_STORY_HEIGHT_FT = 11.0


def _effective_stories(
    params: NumericZoningParams,
    height_limit_ft: float | None,
    story_height_ft: float,
) -> tuple[int, str | None]:
    """Resolve the binding number of stories from zoning + any external height cap.

    Stories are limited by the most restrictive of: the zoning ``max_stories``,
    the zoning ``max_height_ft``, and an *external* ``height_limit_ft`` (e.g. the
    San Diego Proposition D 30 ft coastal cap). Height limits are translated to a
    story count via ``story_height_ft``.

    Returns ``(stories, note)``. ``note`` is set only when the *external* coastal
    limit is what bites (reduces stories below the zoning allowance) — the
    informative case worth surfacing; zoning's own height binding is a silent
    correctness improvement.
    """
    zoning_stories = (
        int(params.max_stories) if params.max_stories and params.max_stories > 0 else None
    )

    # Translate any height caps to stories; track which source is binding.
    height_options: list[tuple[float, str]] = []
    if params.max_height_ft and params.max_height_ft > 0:
        height_options.append((params.max_height_ft, "zoning"))
    if height_limit_ft and height_limit_ft > 0:
        height_options.append((height_limit_ft, "coastal"))

    height_stories: int | None = None
    binding_source: str | None = None
    if height_options:
        binding_height, binding_source = min(height_options, key=lambda h: h[0])
        height_stories = max(1, math.floor(binding_height / story_height_ft))

    candidates = [s for s in (zoning_stories, height_stories) if s is not None]
    stories = max(1, min(candidates)) if candidates else 1

    note: str | None = None
    if (
        binding_source == "coastal"
        and height_stories is not None
        and stories == height_stories
        and (zoning_stories is None or height_stories < zoning_stories)
    ):
        plural = "story" if stories == 1 else "stories"
        note = (
            f"Coastal height limit {height_limit_ft:g} ft caps the building to {stories} "
            f"{plural} (~{story_height_ft:g} ft/story), reducing the buildable envelope."
        )
    return stories, note


def parse_lot_dimensions(dims: str) -> tuple[float | None, float | None]:
    """Parse lot dimensions string like '75 x 100' into (width, depth).

    Returns (None, None) if the string can't be parsed.
    """
    if not dims:
        return None, None
    m = re.search(r"([\d.]+)\s*x\s*([\d.]+)", dims, re.IGNORECASE)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def _reconcile_density(
    max_density_units_per_acre: float | None,
    min_lot_area_per_unit_sqft: float | None,
    *,
    density_verified: bool = False,
    min_lot_area_verified: bool = False,
) -> tuple[float | None, float | None, str | None]:
    """Reconcile the two encodings of the same density limit.

    Density (units/acre) and minimum-lot-area-per-unit (sqft/DU) describe the
    *same* limit. A code states it one way; if the LLM extracted both and they
    contradict (>25%), one is an extraction artifact — applying both as
    independent constraints lets the wrong one silently govern.

    Resolution when they contradict: prefer whichever encoding is *source-
    verified*; if neither is verified, trust min-lot-area (the granular form
    most codes — including San Diego — publish). Returns a consistent
    ``(effective_density, effective_min_lot_area, note)`` so both downstream
    constraints agree. Values pass through unchanged when they agree or only
    one is present.
    """
    if not (max_density_units_per_acre and max_density_units_per_acre > 0):
        return max_density_units_per_acre, min_lot_area_per_unit_sqft, None
    if not (min_lot_area_per_unit_sqft and min_lot_area_per_unit_sqft > 0):
        return max_density_units_per_acre, min_lot_area_per_unit_sqft, None

    implied = SQFT_PER_ACRE / min_lot_area_per_unit_sqft
    hi = max(implied, max_density_units_per_acre)
    lo = min(implied, max_density_units_per_acre)
    if hi <= 0 or (hi - lo) / hi <= 0.25:
        return max_density_units_per_acre, min_lot_area_per_unit_sqft, None

    if density_verified and not min_lot_area_verified:
        eff_density = max_density_units_per_acre
        eff_min_lot = SQFT_PER_ACRE / max_density_units_per_acre
        basis = "density (source-verified)"
    else:
        eff_density = implied
        eff_min_lot = min_lot_area_per_unit_sqft
        basis = "min lot area" + (" (source-verified)" if min_lot_area_verified else "")

    note = (
        f"Density {max_density_units_per_acre:g} u/ac contradicts min lot area "
        f"{min_lot_area_per_unit_sqft:,.0f} sqft/unit (≈ {implied:.1f} u/ac); using {basis}."
    )
    return eff_density, eff_min_lot, note


@trace(name="calculate_max_units", span_type="TOOL")
def calculate_max_units(
    lot_size_sqft: float,
    params: NumericZoningParams | DistrictDimensionalStandard,
    lot_width_ft: float | None = None,
    lot_depth_ft: float | None = None,
    *,
    density_verified: bool = False,
    min_lot_area_verified: bool = False,
    height_limit_ft: float | None = None,
    story_height_ft: float = RESIDENTIAL_STORY_HEIGHT_FT,
    origin: str | None = None,
) -> DensityAnalysis:
    """Calculate maximum allowable dwelling units from zoning parameters.

    ``params`` is the zoning input and may be either:

    * a ``DistrictDimensionalStandard`` — the verified-fact source, a typed row
      extracted from the ordinance's Schedule of District Regulations at
      ingestion time. The resulting ``DensityAnalysis`` is labeled
      ``origin="local_authority"`` (verified-fact grade, not LLM-extracted),
      and its density / min-lot-area are treated as source-verified so the
      verified-entitlement-governs logic activates. This is the seam (WIRE-1.1b)
      where the typed verified-fact row replaces LLM extraction at query time.
    * a ``NumericZoningParams`` — the legacy LLM-extracted path, the fallback
      when no typed standard is available for the parcel's district. The result
      is labeled ``origin="unknown"`` (assumption grade).

    ``density_verified`` / ``min_lot_area_verified`` let the caller pass source-
    verification status so a contradiction between the two density encodings is
    resolved in favor of the corroborated one. When a ``DistrictDimensionalStandard``
    is supplied these flags are forced ``True`` (the typed row IS the authority).
    ``origin`` overrides the inferred provenance label — used by a caller that
    converted a typed standard via ``.to_numeric_zoning_params()`` itself to
    preserve the ``local_authority`` labeling without re-passing the standard.

    Evaluates every applicable constraint and returns the minimum (governing).

    ``height_limit_ft`` is an *external* height cap that overrides the zoning
    height when more restrictive — e.g. the San Diego Proposition D 30 ft coastal
    limit. It feeds the buildable-envelope constraint by reducing the number of
    stories, and can lower the unit count below base zoning when the envelope
    governs.
    """
    # Accept the typed verified-fact source directly: convert it to the
    # calculator's input type and mark the result local_authority (WIRE-1.1b).
    # A caller may either pass the standard here or convert it via
    # .to_numeric_zoning_params() and pass ``origin="local_authority"``.
    from_typed_standard = isinstance(params, DistrictDimensionalStandard)
    if isinstance(params, DistrictDimensionalStandard):
        params = params.to_numeric_zoning_params()
        # The typed row is source-verified by construction; its density +
        # min-lot-area are the authority, so the verified-entitlement-governs
        # logic activates and a contradiction resolves in their favor.
        density_verified = True
        min_lot_area_verified = True
    provenance = (
        origin if origin is not None else ("local_authority" if from_typed_standard else "unknown")
    )

    if lot_size_sqft <= 0:
        return DensityAnalysis(
            max_units=0,
            governing_constraint="no_lot_data",
            constraints=[],
            lot_size_sqft=lot_size_sqft,
            origin=provenance,
            notes=["Lot size is zero or negative — cannot calculate."],
        )

    constraints: list[ConstraintResult] = []
    notes: list[str] = []

    # Reconcile density (u/ac) vs min-lot-area (sqft/DU) — same limit, two forms.
    effective_density, effective_min_lot, density_note = _reconcile_density(
        params.max_density_units_per_acre,
        params.min_lot_area_per_unit_sqft,
        density_verified=density_verified,
        min_lot_area_verified=min_lot_area_verified,
    )
    if density_note:
        notes.append(density_note)

    # ── Constraint 1: Density (units per acre) ──
    if effective_density is not None and effective_density > 0:
        lot_acres = lot_size_sqft / SQFT_PER_ACRE
        raw = effective_density * lot_acres
        constraints.append(
            ConstraintResult(
                name="density",
                max_units=max(0, math.floor(raw)),
                raw_value=raw,
                formula=(f"{effective_density:g} units/acre x {lot_acres:.4f} acres = {raw:.2f}"),
            )
        )

    # ── Constraint 2: Minimum lot area per unit ──
    if effective_min_lot is not None and effective_min_lot > 0:
        raw = lot_size_sqft / effective_min_lot
        constraints.append(
            ConstraintResult(
                name="min_lot_area",
                max_units=max(0, math.floor(raw)),
                raw_value=raw,
                formula=(
                    f"{lot_size_sqft:,.0f} sqft / {effective_min_lot:,.0f} sqft/unit = {raw:.2f}"
                ),
            )
        )

    # ── Constraint 3: Floor Area Ratio ──
    if (
        params.far is not None
        and params.far > 0
        and params.min_unit_size_sqft is not None
        and params.min_unit_size_sqft > 0
    ):
        max_building_sqft = params.far * lot_size_sqft
        raw = max_building_sqft / params.min_unit_size_sqft
        constraints.append(
            ConstraintResult(
                name="floor_area_ratio",
                max_units=max(0, math.floor(raw)),
                raw_value=raw,
                formula=(
                    f"FAR {params.far:g} x {lot_size_sqft:,.0f} sqft = "
                    f"{max_building_sqft:,.0f} sqft / "
                    f"{params.min_unit_size_sqft:,.0f} sqft/unit = {raw:.2f}"
                ),
            )
        )

    # ── Constraint 4: Buildable envelope ──
    buildable_sqft = _calc_buildable_area(
        lot_width_ft,
        lot_depth_ft,
        params,
        notes,
    )
    if (
        buildable_sqft is not None
        and buildable_sqft > 0
        and params.min_unit_size_sqft is not None
        and params.min_unit_size_sqft > 0
    ):
        stories, story_note = _effective_stories(params, height_limit_ft, story_height_ft)
        if story_note:
            notes.append(story_note)
        total_floor_area = buildable_sqft * stories
        raw = total_floor_area / params.min_unit_size_sqft
        constraints.append(
            ConstraintResult(
                name="buildable_envelope",
                max_units=max(0, math.floor(raw)),
                raw_value=raw,
                formula=(
                    f"({buildable_sqft:,.0f} sqft buildable x {stories} stories) / "
                    f"{params.min_unit_size_sqft:,.0f} sqft/unit = {raw:.2f}"
                ),
            )
        )

    # ── Determine governing constraint ──
    if not constraints:
        notes.append("No numeric zoning parameters available for calculation.")
        return DensityAnalysis(
            max_units=0,
            governing_constraint="insufficient_data",
            constraints=[],
            lot_size_sqft=lot_size_sqft,
            buildable_area_sqft=buildable_sqft,
            lot_width_ft=lot_width_ft,
            lot_depth_ft=lot_depth_ft,
            confidence="low",
            origin=provenance,
            notes=notes,
        )

    # The source-verified statutory density / min-lot-area count is the FIRM
    # by-right entitlement. Floor-area-derived counts (buildable envelope, FAR)
    # convert a floor-area cap to units by dividing by an LLM-extracted minimum
    # unit size — and the envelope also uses a deliberately conservative story
    # height. Per the anti-hallucination doctrine, those coarse estimates must not
    # silently override the verified entitlement (this is what made the San Diego
    # Prop D 30 ft coastal cap wrongly cut 6 → 4). When they sit below the verified
    # entitlement we keep the firm count and surface the massing concern instead.
    density_limit_verified = density_verified or min_lot_area_verified
    verified_floor = min(
        (c.max_units for c in constraints if c.name in {"density", "min_lot_area"}),
        default=None,
    )
    governing_pool = constraints
    if density_limit_verified and verified_floor is not None:
        coarse = [
            c
            for c in constraints
            if c.name in {"buildable_envelope", "floor_area_ratio"} and c.max_units < verified_floor
        ]
        if coarse:
            worst = min(coarse, key=lambda c: c.max_units)
            notes.append(
                f"Floor-area estimate ({worst.name}: {worst.max_units} units) is below the "
                f"source-verified entitlement of {verified_floor}. The verified entitlement "
                "governs the firm count; confirm all units fit the massing (height cap / "
                "setbacks / unit size) at design — the estimate uses conservative assumptions."
            )
            demote = {c.name for c in coarse}
            governing_pool = [c for c in constraints if c.name not in demote]

    # Governing = constraint with fewest max_units (excluding demoted estimates)
    governing = min(governing_pool, key=lambda c: c.max_units)
    governing.is_governing = True

    # Confidence based on how many constraints we could evaluate
    if len(constraints) >= 3:
        confidence = "high"
    elif len(constraints) == 2:
        confidence = "medium"
    else:
        confidence = "low"

    # A reconciled density contradiction is a data-quality flag — never claim
    # "high" confidence on top of it.
    if density_note and confidence == "high":
        confidence = "medium"

    return DensityAnalysis(
        max_units=governing.max_units,
        governing_constraint=governing.name,
        constraints=constraints,
        lot_size_sqft=lot_size_sqft,
        buildable_area_sqft=buildable_sqft,
        lot_width_ft=lot_width_ft,
        lot_depth_ft=lot_depth_ft,
        confidence=confidence,
        origin=provenance,
        notes=notes,
    )


@trace(name="calculate_max_gla", span_type="TOOL")
def calculate_max_gla(
    lot_size_sqft: float,
    params: NumericZoningParams,
    lot_width_ft: float | None = None,
    lot_depth_ft: float | None = None,
    *,
    height_limit_ft: float | None = None,
    story_height_ft: float = RESIDENTIAL_STORY_HEIGHT_FT,
) -> DensityAnalysis:
    """Calculate maximum gross leasable area for commercial properties.

    Evaluates FAR, lot coverage, buildable envelope, and explicit GLA cap.
    Returns the minimum (governing constraint). ``height_limit_ft`` (e.g. the
    San Diego Prop D 30 ft coastal cap) reduces stories for the coverage- and
    envelope-based GLA when more restrictive than zoning.
    """
    if lot_size_sqft <= 0:
        return DensityAnalysis(
            max_units=0,
            governing_constraint="no_lot_data",
            constraints=[],
            lot_size_sqft=lot_size_sqft,
            notes=["Lot size is zero or negative — cannot calculate."],
        )

    constraints: list[ConstraintResult] = []
    notes: list[str] = []
    stories, story_note = _effective_stories(params, height_limit_ft, story_height_ft)
    if story_note:
        notes.append(story_note)

    # Constraint 1: FAR
    if params.far is not None and params.far > 0:
        gla = params.far * lot_size_sqft
        constraints.append(
            ConstraintResult(
                name="floor_area_ratio",
                max_units=0,
                raw_value=gla,
                formula=f"FAR {params.far:g} x {lot_size_sqft:,.0f} sqft = {gla:,.0f} sqft GLA",
            )
        )

    # Constraint 2: Lot coverage
    if params.max_lot_coverage_pct is not None and params.max_lot_coverage_pct > 0:
        footprint = (params.max_lot_coverage_pct / 100) * lot_size_sqft
        gla = footprint * stories
        constraints.append(
            ConstraintResult(
                name="lot_coverage",
                max_units=0,
                raw_value=gla,
                formula=(
                    f"{params.max_lot_coverage_pct:g}% x {lot_size_sqft:,.0f} sqft = "
                    f"{footprint:,.0f} sqft footprint x {stories} stories = {gla:,.0f} sqft GLA"
                ),
            )
        )

    # Constraint 3: Buildable envelope
    buildable_sqft = _calc_buildable_area(lot_width_ft, lot_depth_ft, params, notes)
    if buildable_sqft is not None and buildable_sqft > 0:
        gla = buildable_sqft * stories
        constraints.append(
            ConstraintResult(
                name="buildable_envelope",
                max_units=0,
                raw_value=gla,
                formula=f"{buildable_sqft:,.0f} sqft buildable x {stories} stories = {gla:,.0f} sqft GLA",
            )
        )

    # Constraint 4: Explicit GLA cap
    if params.max_gla_sqft is not None and params.max_gla_sqft > 0:
        constraints.append(
            ConstraintResult(
                name="explicit_gla_cap",
                max_units=0,
                raw_value=params.max_gla_sqft,
                formula=f"Explicit GLA cap: {params.max_gla_sqft:,.0f} sqft",
            )
        )

    if not constraints:
        notes.append("No numeric zoning parameters available for GLA calculation.")
        return DensityAnalysis(
            max_units=0,
            governing_constraint="insufficient_data",
            constraints=[],
            lot_size_sqft=lot_size_sqft,
            buildable_area_sqft=buildable_sqft,
            lot_width_ft=lot_width_ft,
            lot_depth_ft=lot_depth_ft,
            confidence="low",
            notes=notes,
        )

    governing = min(constraints, key=lambda c: c.raw_value)
    governing.is_governing = True
    max_gla = governing.raw_value

    confidence = "high" if len(constraints) >= 3 else "medium" if len(constraints) == 2 else "low"

    return DensityAnalysis(
        max_units=0,
        governing_constraint=governing.name,
        constraints=constraints,
        lot_size_sqft=lot_size_sqft,
        buildable_area_sqft=buildable_sqft,
        lot_width_ft=lot_width_ft,
        lot_depth_ft=lot_depth_ft,
        max_gla_sqft=max_gla,
        confidence=confidence,
        notes=notes,
    )


def _calc_buildable_area(
    lot_width_ft: float | None,
    lot_depth_ft: float | None,
    params: NumericZoningParams,
    notes: list[str],
) -> float | None:
    """Calculate buildable area after setbacks are subtracted."""
    if lot_width_ft is None or lot_depth_ft is None:
        return None
    if lot_width_ft <= 0 or lot_depth_ft <= 0:
        return None

    front = params.setback_front_ft or 0
    rear = params.setback_rear_ft or 0
    # Side setback applies to both sides
    side = params.setback_side_ft or 0

    buildable_width = lot_width_ft - (2 * side)
    buildable_depth = lot_depth_ft - front - rear

    if buildable_width <= 0 or buildable_depth <= 0:
        notes.append(
            f"Setbacks ({front}' front, {rear}' rear, {side}' each side) "
            f"exceed lot dimensions ({lot_width_ft}' x {lot_depth_ft}')."
        )
        return 0.0

    return buildable_width * buildable_depth
