"""Deterministic max-allowable-units calculator.

Pure functions — no I/O. Takes lot dimensions + NumericZoningParams,
returns DensityAnalysis with constraint breakdown.

The governing constraint is whichever yields the fewest units.
"""

import math
import re

import mlflow
from mlflow.entities import SpanType

from plotlot.core.types import ConstraintResult, DensityAnalysis, NumericZoningParams

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


@mlflow.trace(name="calculate_max_units", span_type=SpanType.TOOL)
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

    # ── Constraint 1: Density (units per acre) ──
    if params.max_density_units_per_acre is not None and params.max_density_units_per_acre > 0:
        lot_acres = lot_size_sqft / SQFT_PER_ACRE
        raw = params.max_density_units_per_acre * lot_acres
        constraints.append(ConstraintResult(
            name="density",
            max_units=max(1, math.floor(raw)),
            raw_value=raw,
            formula=(
                f"{params.max_density_units_per_acre:g} units/acre "
                f"x {lot_acres:.4f} acres = {raw:.2f}"
            ),
        ))

    # ── Constraint 2: Minimum lot area per unit ──
    if params.min_lot_area_per_unit_sqft is not None and params.min_lot_area_per_unit_sqft > 0:
        raw = lot_size_sqft / params.min_lot_area_per_unit_sqft
        constraints.append(ConstraintResult(
            name="min_lot_area",
            max_units=max(1, math.floor(raw)),
            raw_value=raw,
            formula=(
                f"{lot_size_sqft:,.0f} sqft / "
                f"{params.min_lot_area_per_unit_sqft:,.0f} sqft/unit = {raw:.2f}"
            ),
        ))

    # ── Constraint 3: Floor Area Ratio ──
    if (
        params.far is not None and params.far > 0
        and params.min_unit_size_sqft is not None and params.min_unit_size_sqft > 0
    ):
        max_building_sqft = params.far * lot_size_sqft
        raw = max_building_sqft / params.min_unit_size_sqft
        constraints.append(ConstraintResult(
            name="floor_area_ratio",
            max_units=max(1, math.floor(raw)),
            raw_value=raw,
            formula=(
                f"FAR {params.far:g} x {lot_size_sqft:,.0f} sqft = "
                f"{max_building_sqft:,.0f} sqft / "
                f"{params.min_unit_size_sqft:,.0f} sqft/unit = {raw:.2f}"
            ),
        ))

    # ── Constraint 4: Buildable envelope ──
    buildable_sqft = _calc_buildable_area(
        lot_width_ft, lot_depth_ft, params, notes,
    )
    if (
        buildable_sqft is not None and buildable_sqft > 0
        and params.min_unit_size_sqft is not None and params.min_unit_size_sqft > 0
    ):
        stories = params.max_stories if params.max_stories and params.max_stories > 0 else 1
        total_floor_area = buildable_sqft * stories
        raw = total_floor_area / params.min_unit_size_sqft
        constraints.append(ConstraintResult(
            name="buildable_envelope",
            max_units=max(1, math.floor(raw)),
            raw_value=raw,
            formula=(
                f"({buildable_sqft:,.0f} sqft buildable x {stories} stories) / "
                f"{params.min_unit_size_sqft:,.0f} sqft/unit = {raw:.2f}"
            ),
        ))

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
