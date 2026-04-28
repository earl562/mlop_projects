"""Document generation endpoints — LOI, PSA, Deal Summary, Pro Forma.

Wires the clause builder engine into the HTTP API with:
- POST /api/v1/documents/generate — Download .docx or .xlsx
- POST /api/v1/documents/preview — JSON preview of rendered clauses
- GET  /api/v1/documents/templates — Available document types + required fields
"""

from __future__ import annotations

import io
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from plotlot.api.schemas import (
    DocumentGenerateRequest,
    DocumentPreviewResponse,
    DocumentTemplateInfo,
)
from plotlot.clauses.engine import assemble_clauses, assemble_document
from plotlot.clauses.loader import ClauseRegistry
from plotlot.clauses.schema import (
    AssemblyConfig,
    DealContext,
    DealType,
    DocumentType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Lazy-loaded registry (loaded once on first request)
_registry: ClauseRegistry | None = None


def _get_registry() -> ClauseRegistry:
    global _registry
    if _registry is None:
        _registry = ClauseRegistry.from_directory()
        logger.info("Loaded clause registry: %d clauses", len(_registry))
    return _registry


def _safe_float(value: object, field: str) -> float:
    """Safely coerce a context value to float, raising HTTPException(400) on failure."""
    if value is None or isinstance(value, (list, dict)):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value for numeric field '{field}': expected number, got {type(value).__name__}",
        )
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value for numeric field '{field}': {value!r}",
        ) from e


def _safe_int(value: object, field: str) -> int:
    """Safely coerce a context value to int, raising HTTPException(400) on failure."""
    if value is None or isinstance(value, (list, dict)):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value for numeric field '{field}': expected integer, got {type(value).__name__}",
        )
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value for numeric field '{field}': {value!r}",
        ) from e


def _build_deal_context(req: DocumentGenerateRequest) -> DealContext:
    """Convert API request into a DealContext for the clause engine."""
    ctx = req.context
    return DealContext(
        # Property
        property_address=ctx.get("property_address", ""),
        formatted_address=ctx.get("formatted_address", ""),
        apn=ctx.get("apn", ""),
        legal_description=ctx.get("legal_description", ""),
        municipality=ctx.get("municipality", ""),
        county=ctx.get("county", ""),
        state_code=ctx.get("state_code", "FL"),
        lot_size_sqft=_safe_float(ctx.get("lot_size_sqft", 0), "lot_size_sqft"),
        year_built=_safe_int(ctx.get("year_built", 0), "year_built"),
        owner=ctx.get("owner", ""),
        # Zoning
        zoning_district=ctx.get("zoning_district", ""),
        zoning_description=ctx.get("zoning_description", ""),
        max_units=_safe_int(ctx.get("max_units", 0), "max_units"),
        governing_constraint=ctx.get("governing_constraint", ""),
        max_height=ctx.get("max_height", ""),
        max_density=ctx.get("max_density", ""),
        # Comps
        median_price_per_acre=_safe_float(
            ctx.get("median_price_per_acre", 0), "median_price_per_acre"
        ),
        estimated_land_value=_safe_float(
            ctx.get("estimated_land_value", 0), "estimated_land_value"
        ),
        comp_count=_safe_int(ctx.get("comp_count", 0), "comp_count"),
        # Pro forma
        gross_development_value=_safe_float(
            ctx.get("gross_development_value", 0), "gross_development_value"
        ),
        hard_costs=_safe_float(ctx.get("hard_costs", 0), "hard_costs"),
        soft_costs=_safe_float(ctx.get("soft_costs", 0), "soft_costs"),
        builder_margin=_safe_float(ctx.get("builder_margin", 0), "builder_margin"),
        max_land_price=_safe_float(ctx.get("max_land_price", 0), "max_land_price"),
        cost_per_door=_safe_float(ctx.get("cost_per_door", 0), "cost_per_door"),
        adv_per_unit=_safe_float(ctx.get("adv_per_unit", 0), "adv_per_unit"),
        # Parties
        buyer_name=ctx.get("buyer_name", ""),
        buyer_entity=ctx.get("buyer_entity", ""),
        buyer_email=ctx.get("buyer_email", ""),
        buyer_phone=ctx.get("buyer_phone", ""),
        buyer_address=ctx.get("buyer_address", ""),
        seller_name=ctx.get("seller_name", ""),
        seller_email=ctx.get("seller_email", ""),
        seller_address=ctx.get("seller_address", ""),
        # Financial
        purchase_price=_safe_float(ctx.get("purchase_price", 0), "purchase_price"),
        earnest_money=_safe_float(ctx.get("earnest_money", 0), "earnest_money"),
        down_payment=_safe_float(ctx.get("down_payment", 0), "down_payment"),
        cash_at_closing=_safe_float(ctx.get("cash_at_closing", 0), "cash_at_closing"),
        # Financing
        deal_type=DealType(req.deal_type),
        financing_type=ctx.get("financing_type", ""),
        existing_mortgage_balance_1=_safe_float(
            ctx.get("existing_mortgage_balance_1", 0), "existing_mortgage_balance_1"
        ),
        existing_mortgage_payment=_safe_float(
            ctx.get("existing_mortgage_payment", 0), "existing_mortgage_payment"
        ),
        existing_mortgage_rate=_safe_float(
            ctx.get("existing_mortgage_rate", 0), "existing_mortgage_rate"
        ),
        seller_carryback_amount=_safe_float(
            ctx.get("seller_carryback_amount", 0), "seller_carryback_amount"
        ),
        seller_carryback_rate=_safe_float(
            ctx.get("seller_carryback_rate", 0), "seller_carryback_rate"
        ),
        seller_carryback_term_months=_safe_int(
            ctx.get("seller_carryback_term_months", 0), "seller_carryback_term_months"
        ),
        seller_carryback_payment=_safe_float(
            ctx.get("seller_carryback_payment", 0), "seller_carryback_payment"
        ),
        # Periods
        inspection_days=_safe_int(ctx.get("inspection_days", 30), "inspection_days"),
        closing_days=_safe_int(ctx.get("closing_days", 60), "closing_days"),
        feasibility_days=_safe_int(ctx.get("feasibility_days", 45), "feasibility_days"),
        # Escrow
        escrow_agent_name=ctx.get("escrow_agent_name", ""),
        escrow_agent_address=ctx.get("escrow_agent_address", ""),
        escrow_agent_phone=ctx.get("escrow_agent_phone", ""),
        escrow_agent_email=ctx.get("escrow_agent_email", ""),
        # AI
        summary=ctx.get("summary", ""),
        confidence=ctx.get("confidence", ""),
    )


# ---------------------------------------------------------------------------
# Templates endpoint
# ---------------------------------------------------------------------------

_TEMPLATE_INFO: list[DocumentTemplateInfo] = [
    DocumentTemplateInfo(
        document_type="loi",
        label="Letter of Intent",
        description="Non-binding LOI for property acquisition with financing terms",
        supported_deal_types=[
            "land_deal",
            "subject_to",
            "wrap",
            "hybrid",
            "seller_finance",
            "wholesale",
        ],
        supported_formats=["docx"],
        required_fields=["property_address"],
        optional_fields=["buyer_name", "seller_name", "purchase_price", "financing_type"],
    ),
    DocumentTemplateInfo(
        document_type="psa",
        label="Purchase and Sale Agreement",
        description="Full PSA with mutually exclusive financing clauses for any deal type",
        supported_deal_types=[
            "subject_to",
            "wrap",
            "hybrid",
            "seller_finance",
            "wholesale",
            "land_deal",
        ],
        supported_formats=["docx"],
        required_fields=["property_address", "buyer_name", "seller_name"],
        optional_fields=["purchase_price", "financing_type", "inspection_days", "closing_days"],
    ),
    DocumentTemplateInfo(
        document_type="deal_summary",
        label="Deal Summary Report",
        description="PlotLot analysis report with zoning, density, comps, and pro forma",
        supported_deal_types=["land_deal", "subject_to", "wrap", "hybrid", "seller_finance"],
        supported_formats=["docx"],
        required_fields=["property_address"],
        optional_fields=["zoning_district", "max_units", "median_price_per_acre"],
    ),
    DocumentTemplateInfo(
        document_type="proforma_spreadsheet",
        label="Pro Forma Spreadsheet",
        description="Multi-sheet financial pro forma with sensitivity analysis",
        supported_deal_types=["land_deal", "subject_to", "wrap", "hybrid", "seller_finance"],
        supported_formats=["xlsx"],
        required_fields=["property_address"],
        optional_fields=["gross_development_value", "hard_costs", "purchase_price"],
    ),
]


@router.get("/templates", response_model=list[DocumentTemplateInfo])
async def list_templates():
    """List available document types with their required fields and formats."""
    return _TEMPLATE_INFO


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------


@router.post("/preview", response_model=DocumentPreviewResponse)
async def preview_document(req: DocumentGenerateRequest):
    """Preview rendered clause text without generating a file."""
    try:
        doc_type = DocumentType(req.document_type)
        deal_type = DealType(req.deal_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    registry = _get_registry()
    context = _build_deal_context(req)
    config = AssemblyConfig(
        document_type=doc_type,
        deal_type=deal_type,
        state_code=req.context.get("state_code", "FL"),
    )

    rendered = assemble_clauses(config, context, registry)

    return DocumentPreviewResponse(
        document_type=req.document_type,
        deal_type=req.deal_type,
        clause_count=len(rendered),
        clauses=[{"id": c.id, "title": c.title, "content": c.rendered_content} for c in rendered],
    )


# ---------------------------------------------------------------------------
# Generate endpoint (file download)
# ---------------------------------------------------------------------------


@router.post("/generate")
async def generate_document(req: DocumentGenerateRequest):
    """Generate and download a document (.docx or .xlsx).

    Returns a StreamingResponse with the binary file.
    """
    registry = _get_registry()
    context = _build_deal_context(req)

    # Determine output format
    doc_type = DocumentType(req.document_type)
    output_format = req.output_format or (
        "xlsx" if doc_type == DocumentType.proforma_spreadsheet else "docx"
    )

    config = AssemblyConfig(
        document_type=doc_type,
        deal_type=DealType(req.deal_type),
        state_code=req.context.get("state_code", "FL"),
        output_format=output_format,
    )

    try:
        doc = await assemble_document(config, context, registry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    from plotlot.clauses.renderers.sheets_renderer import SheetsProFormaResult

    if isinstance(doc, SheetsProFormaResult):
        return JSONResponse(
            content={
                "spreadsheet_id": doc.spreadsheet_id,
                "spreadsheet_url": doc.spreadsheet_url,
                "title": doc.title,
            }
        )

    return StreamingResponse(
        io.BytesIO(doc.data),
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.filename}"',
            "Content-Length": str(len(doc.data)),
        },
    )
