"""Geometry endpoints — buildable envelope computation, PDF export, pro forma.

Computes 3D geometry for the buildable envelope viewer given lot dimensions,
setbacks, and zoning constraints (height, FAR, coverage).  Also provides
PDF export for zoning reports and pro forma financing documents.
"""

import io
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from plotlot.api.schemas import (
    EnvelopeGeometry,
    EnvelopeRequest,
    EnvelopeVertex,
    FloorPlanRequest as FloorPlanRequestSchema,
    FloorPlanResponse,
    FloorPlanUnitResponse,
    ProFormaRequest,
    ProFormaResponse,
    ZoningReportResponse,
)
from plotlot.documents.pdf_export import generate_zoning_pdf
from plotlot.documents.proforma import (
    ProFormaInput,
    compute_pro_forma,
    generate_pro_forma_pdf,
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


# ---------------------------------------------------------------------------
# PDF Report Export (F1)
# ---------------------------------------------------------------------------


@router.post("/report/pdf")
async def export_report_pdf(report: ZoningReportResponse):
    """Export a zoning report as a branded PDF."""
    pdf_bytes = generate_zoning_pdf(report.model_dump())
    address_slug = (
        (report.formatted_address or report.address or "report")
        .replace(" ", "_")
        .replace(",", "")[:50]
    )
    filename = f"PlotLot_{address_slug}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Pro Forma (F3)
# ---------------------------------------------------------------------------


def _request_to_input(request: ProFormaRequest) -> ProFormaInput:
    """Convert API request schema to internal ProFormaInput dataclass."""
    return ProFormaInput(
        address=request.address,
        municipality=request.municipality,
        county=request.county,
        zoning_district=request.zoning_district,
        lot_size_sqft=request.lot_size_sqft,
        max_units=request.max_units,
        unit_size_sqft=request.unit_size_sqft,
        stories=request.stories,
        parking_spaces=request.parking_spaces,
        land_cost=request.land_cost,
        construction_cost_psf=request.construction_cost_psf,
        soft_cost_pct=request.soft_cost_pct,
        contingency_pct=request.contingency_pct,
        ltv_pct=request.ltv_pct,
        interest_rate_pct=request.interest_rate_pct,
        loan_term_years=request.loan_term_years,
        monthly_rent_per_unit=request.monthly_rent_per_unit,
        sale_price_per_unit=request.sale_price_per_unit,
        vacancy_pct=request.vacancy_pct,
        operating_expense_pct=request.operating_expense_pct,
        narrative=request.narrative,
    )


@router.post("/proforma", response_model=ProFormaResponse)
async def compute_proforma(request: ProFormaRequest):
    """Compute pro forma development analysis."""
    inp = _request_to_input(request)
    result = compute_pro_forma(inp)
    return ProFormaResponse(
        total_buildable_sqft=result.total_buildable_sqft,
        hard_costs=result.hard_costs,
        soft_costs=result.soft_costs,
        contingency=result.contingency,
        total_development_cost=result.total_development_cost,
        loan_amount=result.loan_amount,
        equity_required=result.equity_required,
        annual_debt_service=result.annual_debt_service,
        gross_annual_income=result.gross_annual_income,
        effective_gross_income=result.effective_gross_income,
        operating_expenses=result.operating_expenses,
        net_operating_income=result.net_operating_income,
        cap_rate_pct=result.cap_rate_pct,
        cash_on_cash_pct=result.cash_on_cash_pct,
        total_sale_revenue=result.total_sale_revenue,
        total_profit=result.total_profit,
        roi_pct=result.roi_pct,
        notes=result.notes,
    )


@router.post("/proforma/pdf")
async def export_proforma_pdf(request: ProFormaRequest):
    """Export pro forma as PDF."""
    inp = _request_to_input(request)
    pdf_bytes = generate_pro_forma_pdf(inp)
    slug = (request.address or "proforma").replace(" ", "_").replace(",", "")[:50]
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="PlotLot_ProForma_{slug}.pdf"'
        },
    )
