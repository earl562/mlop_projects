"""Deterministic max-allowable-units calculator.

Pure functions — no I/O. Takes lot dimensions + NumericZoningParams,
returns DensityAnalysis with constraint breakdown.

The governing constraint is whichever yields the fewest units.
"""

import math
import re

from plotlot.core.types import ConstraintResult, DensityAnalysis, NumericZoningParams
from plotlot.observability.tracing import trace

SQFT_PER_ACRE = 43_560


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


def _derive_max_stories(
    max_height_ft: float | None,
    max_stories: int | None,
) -> int | None:
    """Derive max stories from explicit value or height limit.

    When max_stories is given and positive, it takes precedence.
    Otherwise, derives from max_height_ft using 11 ft/story
    (9 ft ceilings + 16-24" trusses per Danni's methodology).
    Returns None when neither is available.
    """
    if max_stories is not None and max_stories > 0:
        return max_stories
    if max_height_ft is not None and max_height_ft > 0:
        return max(1, int(max_height_ft // 11.0))
    return None


@trace(name="calculate_max_units", span_type="TOOL")
def calculate_max_units(
    lot_size_sqft: float,
    params: NumericZoningParams,
    lot_width_ft: float | None = None,
    lot_depth_ft: float | None = None,
) -> DensityAnalysis:
    """Calculate maximum allowable dwelling units from zoning parameters.

    Evaluates every applicable constraint and returns the minimum (governing).
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

    derived_max_stories = _derive_max_stories(params.max_height_ft, params.max_stories)

    # ── Constraint 1: Density (units per acre) ──
    if params.max_density_units_per_acre is not None and params.max_density_units_per_acre > 0:
        lot_acres = lot_size_sqft / SQFT_PER_ACRE
        raw = params.max_density_units_per_acre * lot_acres
        constraints.append(
            ConstraintResult(
                name="density",
                max_units=math.floor(raw),
                raw_value=raw,
                formula=(
                    f"{params.max_density_units_per_acre:g} units/acre "
                    f"x {lot_acres:.4f} acres = {raw:.2f}"
                ),
            )
        )

    # ── Constraint 2: Minimum lot area per unit ──
    if params.min_lot_area_per_unit_sqft is not None and params.min_lot_area_per_unit_sqft > 0:
        raw = lot_size_sqft / params.min_lot_area_per_unit_sqft
        constraints.append(
            ConstraintResult(
                name="min_lot_area",
                max_units=math.floor(raw),
                raw_value=raw,
                formula=(
                    f"{lot_size_sqft:,.0f} sqft / "
                    f"{params.min_lot_area_per_unit_sqft:,.0f} sqft/unit = {raw:.2f}"
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
                max_units=math.floor(raw),
                raw_value=raw,
                formula=(
                    f"FAR {params.far:g} x {lot_size_sqft:,.0f} sqft = "
                    f"{max_building_sqft:,.0f} sqft / "
                    f"{params.min_unit_size_sqft:,.0f} sqft/unit = {raw:.2f}"
                ),
            )
        )

    # ── Constraint 4: Lot coverage ──
    if (
        params.max_lot_coverage_pct is not None
        and params.max_lot_coverage_pct > 0
        and lot_size_sqft > 0
    ):
        coverage_footprint = (params.max_lot_coverage_pct / 100.0) * lot_size_sqft
        if (
            derived_max_stories is not None
            and params.min_unit_size_sqft is not None
            and params.min_unit_size_sqft > 0
        ):
            raw = coverage_footprint * derived_max_stories / params.min_unit_size_sqft
            constraints.append(
                ConstraintResult(
                    name="lot_coverage",
                    max_units=math.floor(raw),
                    raw_value=raw,
                    formula=(
                        f"{params.max_lot_coverage_pct:g}% x {lot_size_sqft:,.0f} sqft = "
                        f"{coverage_footprint:,.0f} sqft footprint x "
                        f"{derived_max_stories} stories / "
                        f"{params.min_unit_size_sqft:,.0f} sqft/unit = {raw:.2f}"
                    ),
                )
            )

    # ── Constraint 5: Buildable envelope ──
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
        stories = derived_max_stories if derived_max_stories is not None else 1
        total_floor_area = buildable_sqft * stories
        raw = total_floor_area / params.min_unit_size_sqft
        constraints.append(
            ConstraintResult(
                name="buildable_envelope",
                max_units=math.floor(raw),
                raw_value=raw,
                formula=(
                    f"({buildable_sqft:,.0f} sqft buildable x {stories} stories) / "
                    f"{params.min_unit_size_sqft:,.0f} sqft/unit = {raw:.2f}"
                ),
            )
        )

    # ── Constraint 6: Parking ──
    if (
        params.parking_spaces_per_unit is not None
        and params.parking_spaces_per_unit > 0
        and buildable_sqft is not None
        and buildable_sqft > 0
        and params.min_unit_size_sqft is not None
        and params.min_unit_size_sqft > 0
    ):
        stories = derived_max_stories if derived_max_stories is not None else 1
        envelope_max_units_raw = buildable_sqft * stories / params.min_unit_size_sqft
        envelope_max_units = math.floor(envelope_max_units_raw)
        parking_area_per_unit = params.parking_spaces_per_unit * 350.0
        parking_consumed = envelope_max_units * parking_area_per_unit
        effective_buildable = max(0.0, buildable_sqft - parking_consumed)
        raw = effective_buildable * stories / params.min_unit_size_sqft
        parking_constrained_units = math.floor(raw)
        constraints.append(
            ConstraintResult(
                name="parking",
                max_units=min(envelope_max_units, parking_constrained_units),
                raw_value=raw,
                formula=(
                    f"{params.parking_spaces_per_unit:g} spaces/unit x 350 sqft/space = "
                    f"{parking_area_per_unit:,.0f} sqft/unit; "
                    f"{envelope_max_units} units x {parking_area_per_unit:,.0f} sqft/unit = "
                    f"{parking_consumed:,.0f} sqft parking; "
                    f"buildable {buildable_sqft:,.0f} - parking {parking_consumed:,.0f} = "
                    f"{effective_buildable:,.0f} sqft x {stories} stories / "
                    f"{params.min_unit_size_sqft:,.0f} sqft/unit = {parking_constrained_units}"
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
            notes=notes,
        )

    # Governing = constraint with fewest max_units
    governing = min(constraints, key=lambda c: c.max_units)
    governing.is_governing = True

    # Confidence based on how many constraints we could evaluate
    if len(constraints) >= 3:
        confidence = "high"
    elif len(constraints) == 2:
        confidence = "medium"
    else:
        confidence = "low"

    if governing.max_units < 1:
        notes.append("Lot too small for any unit under current zoning.")

    return DensityAnalysis(
        max_units=governing.max_units,
        governing_constraint=governing.name,
        constraints=constraints,
        lot_size_sqft=lot_size_sqft,
        buildable_area_sqft=buildable_sqft,
        lot_width_ft=lot_width_ft,
        lot_depth_ft=lot_depth_ft,
        confidence=confidence,
        notes=notes,
    )


@trace(name="calculate_max_gla", span_type="TOOL")
def calculate_max_gla(
    lot_size_sqft: float,
    params: NumericZoningParams,
    lot_width_ft: float | None = None,
    lot_depth_ft: float | None = None,
) -> DensityAnalysis:
    """Calculate maximum gross leasable area for commercial properties.

    Evaluates FAR, lot coverage, buildable envelope, and explicit GLA cap.
    Returns the minimum (governing constraint).
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
    stories = params.max_stories if params.max_stories and params.max_stories > 0 else 1

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
