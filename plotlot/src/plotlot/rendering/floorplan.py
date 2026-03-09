"""Parametric floor plan generator.

Takes buildable envelope dimensions + zoning constraints and generates
unit layouts. Uses Shapely for 2D geometry, outputs SVG for frontend display.

Templates:
- single_family: 1 unit filling the buildable footprint
- duplex: 2 side-by-side or stacked units
- small_multifamily: 3-8 units with corridor layout
"""

import logging
from dataclasses import dataclass, field

from shapely.geometry import Polygon, box

logger = logging.getLogger(__name__)


@dataclass
class UnitLayout:
    """A single dwelling unit within the floor plan."""

    unit_id: str
    polygon: Polygon
    area_sqft: float
    width_ft: float
    depth_ft: float
    floor: int = 1
    label: str = ""


@dataclass
class FloorPlan:
    """Complete floor plan result."""

    template: str
    units: list[UnitLayout]
    total_units: int
    buildable_width_ft: float
    buildable_depth_ft: float
    max_height_ft: float
    stories: int
    parking_spaces: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class FloorPlanRequest:
    """Input parameters for floor plan generation."""

    buildable_width_ft: float
    buildable_depth_ft: float
    max_height_ft: float = 35.0
    max_units: int = 1
    min_unit_size_sqft: float = 400.0
    parking_per_unit: float = 1.5
    story_height_ft: float = 10.0
    template: str = "auto"  # auto, single_family, duplex, small_multifamily


def generate_floor_plan(req: FloorPlanRequest) -> FloorPlan:
    """Generate a parametric floor plan within the buildable envelope.

    Selects the best template based on max_units if template="auto":
    - 1 unit -> single_family
    - 2 units -> duplex
    - 3+ units -> small_multifamily
    """
    template = req.template
    if template == "auto":
        if req.max_units <= 1:
            template = "single_family"
        elif req.max_units <= 2:
            template = "duplex"
        else:
            template = "small_multifamily"

    generators = {
        "single_family": _gen_single_family,
        "duplex": _gen_duplex,
        "small_multifamily": _gen_small_multifamily,
    }

    gen = generators.get(template)
    if gen is None:
        raise ValueError(f"Unknown template: {template}")

    return gen(req)


def _gen_single_family(req: FloorPlanRequest) -> FloorPlan:
    """Single unit filling the buildable footprint."""
    w, d = req.buildable_width_ft, req.buildable_depth_ft
    stories = min(int(req.max_height_ft / req.story_height_ft), 2)  # typical SFH max 2 stories

    poly = box(0, 0, w, d)
    unit = UnitLayout(
        unit_id="A1",
        polygon=poly,
        area_sqft=w * d * stories,
        width_ft=w,
        depth_ft=d,
        floor=1,
        label="Unit A1",
    )

    parking = max(2, int(req.parking_per_unit))  # SFH typically 2-car garage
    notes = [f"{stories}-story single-family home", f"{parking}-car garage"]

    return FloorPlan(
        template="single_family",
        units=[unit],
        total_units=1,
        buildable_width_ft=w,
        buildable_depth_ft=d,
        max_height_ft=req.max_height_ft,
        stories=stories,
        parking_spaces=parking,
        notes=notes,
    )


def _gen_duplex(req: FloorPlanRequest) -> FloorPlan:
    """Two units -- side-by-side if lot is wide enough, otherwise stacked."""
    w, d = req.buildable_width_ft, req.buildable_depth_ft
    stories = min(int(req.max_height_ft / req.story_height_ft), 2)

    # Side-by-side if width >= 30ft (two ~15ft wide units)
    if w >= 30:
        wall_thickness = 1.0  # shared wall
        unit_w = (w - wall_thickness) / 2

        poly_a = box(0, 0, unit_w, d)
        poly_b = box(unit_w + wall_thickness, 0, w, d)

        units = [
            UnitLayout("A1", poly_a, unit_w * d, unit_w, d, 1, "Unit A"),
            UnitLayout("B1", poly_b, unit_w * d, unit_w, d, 1, "Unit B"),
        ]
        layout_type = "side-by-side"
    else:
        # Stacked (if 2 stories allowed)
        if stories >= 2:
            poly = box(0, 0, w, d)
            units = [
                UnitLayout("A1", poly, w * d, w, d, 1, "Unit A (Ground)"),
                UnitLayout("B1", poly, w * d, w, d, 2, "Unit B (Upper)"),
            ]
            layout_type = "stacked"
        else:
            # Front-back split
            wall_thickness = 1.0
            unit_d = (d - wall_thickness) / 2
            poly_a = box(0, 0, w, unit_d)
            poly_b = box(0, unit_d + wall_thickness, w, d)
            units = [
                UnitLayout("A1", poly_a, w * unit_d, w, unit_d, 1, "Unit A (Front)"),
                UnitLayout("B1", poly_b, w * unit_d, w, unit_d, 1, "Unit B (Rear)"),
            ]
            layout_type = "front-back"

    parking = int(req.parking_per_unit * 2)

    # Check min unit size
    notes = [f"{layout_type} duplex"]
    for u in units:
        if u.area_sqft < req.min_unit_size_sqft:
            notes.append(
                f"Warning: {u.label} ({u.area_sqft:.0f} sqft) below min"
                f" {req.min_unit_size_sqft:.0f} sqft"
            )

    return FloorPlan(
        template="duplex",
        units=units,
        total_units=2,
        buildable_width_ft=w,
        buildable_depth_ft=d,
        max_height_ft=req.max_height_ft,
        stories=stories,
        parking_spaces=parking,
        notes=notes,
    )


def _gen_small_multifamily(req: FloorPlanRequest) -> FloorPlan:
    """3-8 units with central corridor layout."""
    w, d = req.buildable_width_ft, req.buildable_depth_ft
    stories = min(int(req.max_height_ft / req.story_height_ft), 3)  # max 3 for small MF

    corridor_width = 5.0  # 5ft central corridor
    wall_thickness = 0.5

    # Units on each side of corridor
    usable_w = w - corridor_width - 2 * wall_thickness
    unit_w = usable_w / 2  # units on each side

    if unit_w < 12:  # too narrow for two-sided corridor
        # Single-loaded corridor (units on one side only)
        unit_w = w - corridor_width - wall_thickness
        units_per_floor_row = 1
    else:
        units_per_floor_row = 2  # double-loaded

    # How many units deep can we fit?
    min_unit_depth = max(12.0, req.min_unit_size_sqft / unit_w) if unit_w > 0 else d
    units_along_depth = max(1, int(d / (min_unit_depth + wall_thickness)))
    unit_d = (d - wall_thickness * (units_along_depth - 1)) / units_along_depth

    units_per_floor = units_along_depth * units_per_floor_row
    target_units = min(req.max_units, units_per_floor * stories)

    units = []
    unit_num = 0
    for floor in range(1, stories + 1):
        if unit_num >= target_units:
            break
        for row in range(units_along_depth):
            if unit_num >= target_units:
                break
            y_offset = row * (unit_d + wall_thickness)

            # Left side unit
            if units_per_floor_row >= 1:
                unit_num += 1
                if unit_num > target_units:
                    break
                poly = box(0, y_offset, unit_w, y_offset + unit_d)
                units.append(
                    UnitLayout(
                        unit_id=f"{floor}{chr(64 + ((unit_num - 1) % units_per_floor) + 1)}",
                        polygon=poly,
                        area_sqft=unit_w * unit_d,
                        width_ft=unit_w,
                        depth_ft=unit_d,
                        floor=floor,
                        label=f"Unit {floor}{chr(64 + ((unit_num - 1) % units_per_floor) + 1)}",
                    )
                )

            # Right side unit (if double-loaded)
            if units_per_floor_row >= 2:
                unit_num += 1
                if unit_num > target_units:
                    break
                x_off = unit_w + wall_thickness + corridor_width + wall_thickness
                poly = box(x_off, y_offset, x_off + unit_w, y_offset + unit_d)
                units.append(
                    UnitLayout(
                        unit_id=f"{floor}{chr(64 + ((unit_num - 1) % units_per_floor) + 1)}",
                        polygon=poly,
                        area_sqft=unit_w * unit_d,
                        width_ft=unit_w,
                        depth_ft=unit_d,
                        floor=floor,
                        label=f"Unit {floor}{chr(64 + ((unit_num - 1) % units_per_floor) + 1)}",
                    )
                )

    parking = int(req.parking_per_unit * len(units))

    notes = [
        f"{len(units)}-unit {'double' if units_per_floor_row == 2 else 'single'}-loaded corridor",
        f"{stories} stories, {units_per_floor} units/floor",
        f"Unit size: {unit_w:.0f} x {unit_d:.0f} ft ({unit_w * unit_d:.0f} sqft)",
    ]

    for u in units:
        if u.area_sqft < req.min_unit_size_sqft:
            notes.append(
                f"Warning: {u.label} ({u.area_sqft:.0f} sqft) below min"
                f" {req.min_unit_size_sqft:.0f} sqft"
            )
            break  # one warning is enough

    return FloorPlan(
        template="small_multifamily",
        units=units,
        total_units=len(units),
        buildable_width_ft=w,
        buildable_depth_ft=d,
        max_height_ft=req.max_height_ft,
        stories=stories,
        parking_spaces=parking,
        notes=notes,
    )


def floor_plan_to_svg(plan: FloorPlan, scale: float = 4.0) -> str:
    """Render a floor plan to SVG string.

    Args:
        plan: The generated floor plan.
        scale: Pixels per foot (default 4px/ft).

    Returns:
        SVG string suitable for embedding in HTML.
    """
    w = plan.buildable_width_ft
    d = plan.buildable_depth_ft

    margin = 40  # px for labels
    svg_w = w * scale + 2 * margin
    svg_h = d * scale + 2 * margin

    # Group floors
    floors: dict[int, list[UnitLayout]] = {}
    for unit in plan.units:
        floors.setdefault(unit.floor, []).append(unit)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w:.0f} {svg_h:.0f}" '
        f'width="{svg_w:.0f}" height="{svg_h:.0f}" style="max-width:100%">',
        "<style>",
        "  .lot { fill: #faf8f5; stroke: #a8a29e; stroke-width: 1; stroke-dasharray: 4,4; }",
        "  .unit { stroke: #78716c; stroke-width: 1.5; }",
        (
            "  .unit-label { font-family: system-ui, sans-serif; font-size: 11px;"
            " fill: #44403c; text-anchor: middle; }"
        ),
        (
            "  .dim-label { font-family: system-ui, sans-serif; font-size: 10px;"
            " fill: #78716c; text-anchor: middle; }"
        ),
        (
            "  .title { font-family: system-ui, sans-serif; font-size: 13px;"
            " font-weight: 600; fill: #292524; }"
        ),
        "</style>",
    ]

    # Colors for different floors
    floor_colors = ["#fef3c7", "#d1fae5", "#dbeafe", "#fce7f3"]  # amber, emerald, blue, pink

    # Only show first floor footprint (all floors have same footprint)
    floor_num = 1  # Show floor 1 layout
    floor_units = floors.get(floor_num, plan.units[:1])

    # Buildable outline (dashed)
    parts.append(
        f'<rect class="lot" x="{margin}" y="{margin}"'
        f' width="{w * scale:.0f}" height="{d * scale:.0f}" />'
    )

    # Draw units
    for unit in floor_units:
        bounds = unit.polygon.bounds  # (minx, miny, maxx, maxy)
        ux = bounds[0] * scale + margin
        uy = bounds[1] * scale + margin
        uw = (bounds[2] - bounds[0]) * scale
        uh = (bounds[3] - bounds[1]) * scale
        color = floor_colors[(unit.floor - 1) % len(floor_colors)]

        parts.append(
            f'<rect class="unit" x="{ux:.1f}" y="{uy:.1f}"'
            f' width="{uw:.1f}" height="{uh:.1f}" fill="{color}" />'
        )

        # Unit label
        cx = ux + uw / 2
        cy = uy + uh / 2
        parts.append(f'<text class="unit-label" x="{cx:.1f}" y="{cy:.1f}">{unit.label}</text>')
        parts.append(
            f'<text class="unit-label" x="{cx:.1f}" y="{cy + 14:.1f}">'
            f"{unit.area_sqft:.0f} sqft</text>"
        )

    # Dimension labels
    # Width along bottom
    parts.append(
        f'<text class="dim-label" x="{margin + w * scale / 2:.0f}"'
        f' y="{margin + d * scale + 16:.0f}">{w:.0f} ft</text>'
    )
    # Depth along right
    parts.append(
        f'<text class="dim-label" x="{margin + w * scale + 16:.0f}"'
        f' y="{margin + d * scale / 2:.0f}"'
        f' transform="rotate(90, {margin + w * scale + 16:.0f},'
        f' {margin + d * scale / 2:.0f})">{d:.0f} ft</text>'
    )

    # Title
    parts.append(
        f'<text class="title" x="{margin}" y="20">'
        f"Floor {floor_num} — {plan.template.replace('_', ' ').title()}</text>"
    )

    parts.append("</svg>")
    return "\n".join(parts)
