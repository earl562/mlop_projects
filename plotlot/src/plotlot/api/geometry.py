"""Geometry endpoints — buildable envelope computation.

Computes 3D geometry for the buildable envelope viewer given lot dimensions,
setbacks, and zoning constraints (height, FAR, coverage).
"""

import logging

from fastapi import APIRouter

from plotlot.api.schemas import (
    EnvelopeGeometry,
    EnvelopeRequest,
    EnvelopeVertex,
    FloorPlanRequest as FloorPlanRequestSchema,
    FloorPlanResponse,
    FloorPlanUnitResponse,
)
from plotlot.rendering.floorplan import (
    FloorPlanRequest as InternalFloorPlanRequest,
    floor_plan_to_svg,
    generate_floor_plan,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/geometry", tags=["geometry"])


@router.post("/envelope", response_model=EnvelopeGeometry)
async def compute_envelope(request: EnvelopeRequest) -> EnvelopeGeometry:
    """Compute buildable envelope geometry from lot dimensions and zoning constraints."""
    w = request.lot_width_ft
    d = request.lot_depth_ft

    # Lot polygon (centered at origin)
    half_w, half_d = w / 2, d / 2
    lot_polygon = [
        EnvelopeVertex(x=-half_w, y=-half_d, z=0),
        EnvelopeVertex(x=half_w, y=-half_d, z=0),
        EnvelopeVertex(x=half_w, y=half_d, z=0),
        EnvelopeVertex(x=-half_w, y=half_d, z=0),
    ]
    lot_area = w * d

    # Setback inset (front = +y side, rear = -y side, sides = ±x)
    sb_f = request.setback_front_ft
    sb_s = request.setback_side_ft
    sb_r = request.setback_rear_ft

    build_w = max(0, w - 2 * sb_s)
    build_d = max(0, d - sb_f - sb_r)

    # Setback polygon (centered, shifted for front/rear asymmetry)
    center_y_offset = (sb_r - sb_f) / 2  # shift if front != rear
    bh_w, bh_d = build_w / 2, build_d / 2
    setback_polygon = [
        EnvelopeVertex(x=-bh_w, y=-bh_d + center_y_offset, z=0),
        EnvelopeVertex(x=bh_w, y=-bh_d + center_y_offset, z=0),
        EnvelopeVertex(x=bh_w, y=bh_d + center_y_offset, z=0),
        EnvelopeVertex(x=-bh_w, y=bh_d + center_y_offset, z=0),
    ]

    buildable_footprint = build_w * build_d
    notes: list[str] = []

    # Apply FAR constraint
    effective_height = request.max_height_ft
    far_limited = False
    if request.floor_area_ratio and lot_area > 0:
        max_floor_area = lot_area * request.floor_area_ratio
        if buildable_footprint > 0:
            far_max_height = max_floor_area / buildable_footprint * 10  # approximate story height
            if far_max_height < effective_height:
                effective_height = far_max_height
                far_limited = True
                notes.append(
                    f"Height limited by FAR ({request.floor_area_ratio}) to {far_max_height:.1f} ft"
                )

    # Apply lot coverage constraint
    coverage_limited = False
    effective_coverage = (buildable_footprint / lot_area * 100) if lot_area > 0 else 0
    if request.lot_coverage_pct and lot_area > 0:
        max_footprint = lot_area * request.lot_coverage_pct / 100
        if buildable_footprint > max_footprint:
            # Scale down the buildable footprint proportionally
            scale = (max_footprint / buildable_footprint) ** 0.5
            build_w *= scale
            build_d *= scale
            buildable_footprint = build_w * build_d
            coverage_limited = True
            effective_coverage = request.lot_coverage_pct
            notes.append(f"Footprint limited by {request.lot_coverage_pct}% lot coverage")
            # Recalculate setback polygon
            bh_w, bh_d = build_w / 2, build_d / 2
            setback_polygon = [
                EnvelopeVertex(x=-bh_w, y=-bh_d + center_y_offset, z=0),
                EnvelopeVertex(x=bh_w, y=-bh_d + center_y_offset, z=0),
                EnvelopeVertex(x=bh_w, y=bh_d + center_y_offset, z=0),
                EnvelopeVertex(x=-bh_w, y=bh_d + center_y_offset, z=0),
            ]

    volume = buildable_footprint * effective_height

    if build_w <= 0 or build_d <= 0:
        notes.append("Warning: setbacks exceed lot dimensions — no buildable area")

    return EnvelopeGeometry(
        lot_polygon=lot_polygon,
        lot_area_sqft=lot_area,
        setback_polygon=setback_polygon,
        buildable_footprint_sqft=buildable_footprint,
        buildable_volume_cuft=volume,
        buildable_width_ft=build_w,
        buildable_depth_ft=build_d,
        max_height_ft=request.max_height_ft,
        effective_height_ft=effective_height,
        effective_coverage_pct=effective_coverage,
        far_limited=far_limited,
        coverage_limited=coverage_limited,
        notes=notes,
    )


@router.post("/floorplan", response_model=FloorPlanResponse)
async def compute_floorplan(request: FloorPlanRequestSchema) -> FloorPlanResponse:
    """Generate a parametric floor plan within the buildable envelope."""
    internal_req = InternalFloorPlanRequest(
        buildable_width_ft=request.buildable_width_ft,
        buildable_depth_ft=request.buildable_depth_ft,
        max_height_ft=request.max_height_ft,
        max_units=request.max_units,
        min_unit_size_sqft=request.min_unit_size_sqft,
        parking_per_unit=request.parking_per_unit,
        story_height_ft=request.story_height_ft,
        template=request.template,
    )

    plan = generate_floor_plan(internal_req)
    svg = floor_plan_to_svg(plan)

    units = [
        FloorPlanUnitResponse(
            unit_id=u.unit_id,
            area_sqft=u.area_sqft,
            width_ft=u.width_ft,
            depth_ft=u.depth_ft,
            floor=u.floor,
            label=u.label,
        )
        for u in plan.units
    ]

    return FloorPlanResponse(
        template=plan.template,
        units=units,
        total_units=plan.total_units,
        buildable_width_ft=plan.buildable_width_ft,
        buildable_depth_ft=plan.buildable_depth_ft,
        max_height_ft=plan.max_height_ft,
        stories=plan.stories,
        parking_spaces=plan.parking_spaces,
        notes=plan.notes,
        svg=svg,
    )
