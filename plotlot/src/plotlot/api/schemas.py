"""Pydantic request/response models for the PlotLot API.

These are the API contract — decoupled from the internal domain dataclasses.
We bridge them using dataclasses.asdict() in the route handlers.
"""

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request body for POST /api/v1/analyze."""

    address: str = Field(
        ...,
        min_length=5,
        max_length=200,
        examples=["171 NE 209th Ter, Miami, FL 33179"],
        description="US property address",
    )
    deal_type: str = Field(
        default="land_deal",
        pattern="^(land_deal|wholesale|creative_finance|hybrid)$",
        description="Deal strategy type",
    )
    skip_steps: list[str] = Field(
        default_factory=list,
        description="Pipeline steps to skip: calculation, comps, proforma",
    )


class SetbacksResponse(BaseModel):
    front: str = ""
    side: str = ""
    rear: str = ""


class ConstraintResponse(BaseModel):
    name: str
    max_units: int
    raw_value: float
    formula: str
    is_governing: bool = False


class MaxAllowableUnitsResponse(BaseModel):
    max_units: int
    governing_constraint: str
    constraints: list[ConstraintResponse]
    lot_size_sqft: float = 0.0
    buildable_area_sqft: float | None = None
    lot_width_ft: float | None = None
    lot_depth_ft: float | None = None
    max_gla_sqft: float | None = None
    confidence: str = "low"
    notes: list[str] = []


class NumericParamsResponse(BaseModel):
    max_density_units_per_acre: float | None = None
    min_lot_area_per_unit_sqft: float | None = None
    far: float | None = None
    max_lot_coverage_pct: float | None = None
    max_height_ft: float | None = None
    max_stories: int | None = None
    setback_front_ft: float | None = None
    setback_side_ft: float | None = None
    setback_rear_ft: float | None = None
    min_unit_size_sqft: float | None = None
    min_lot_width_ft: float | None = None
    parking_spaces_per_unit: float | None = None
    parking_per_1000_gla_sqft: float | None = None
    max_gla_sqft: float | None = None
    min_tenant_size_sqft: float | None = None
    loading_spaces: int | None = None
    property_type: str | None = None


class PropertyRecordResponse(BaseModel):
    folio: str = ""
    address: str = ""
    municipality: str = ""
    county: str = ""
    owner: str = ""
    zoning_code: str = ""
    zoning_description: str = ""
    land_use_code: str = ""
    land_use_description: str = ""
    lot_size_sqft: float = 0.0
    lot_dimensions: str = ""
    bedrooms: int = 0
    bathrooms: float = 0.0
    half_baths: int = 0
    floors: int = 0
    living_units: int = 0
    building_area_sqft: float = 0.0
    living_area_sqft: float = 0.0
    year_built: int = 0
    assessed_value: float = 0.0
    market_value: float = 0.0
    last_sale_price: float = 0.0
    last_sale_date: str = ""
    lat: float | None = None
    lng: float | None = None
    parcel_geometry: list[list[float]] | None = None
    zoning_layer_url: str = ""


class SourceRefResponse(BaseModel):
    """A source ordinance chunk backing an extracted value."""

    section: str = ""
    section_title: str = ""
    chunk_text_preview: str = ""
    score: float = 0.0


class ZoningReportResponse(BaseModel):
    """Full zoning analysis response."""

    address: str
    formatted_address: str
    municipality: str
    county: str
    lat: float | None = None
    lng: float | None = None

    zoning_district: str = ""
    zoning_description: str = ""

    allowed_uses: list[str] = []
    conditional_uses: list[str] = []
    prohibited_uses: list[str] = []

    setbacks: SetbacksResponse = SetbacksResponse()
    max_height: str = ""
    max_density: str = ""
    floor_area_ratio: str = ""
    lot_coverage: str = ""
    min_lot_size: str = ""
    parking_requirements: str = ""

    property_record: PropertyRecordResponse | None = None
    numeric_params: NumericParamsResponse | None = None
    density_analysis: MaxAllowableUnitsResponse | None = None
    comp_analysis: "CompAnalysisResponse | None" = None
    pro_forma: "LandProFormaResponse | None" = None

    summary: str = ""
    sources: list[str] = []
    confidence: str = ""

    # Inline citations — source ordinance chunks backing extracted values
    source_refs: list[SourceRefResponse] = []

    # Progressive autonomy metadata (Klarna confidence-gated pattern)
    confidence_warning: str = ""
    suggested_next_steps: list[str] = []


# ---------------------------------------------------------------------------
# Comparable Sales (Phase 6A)
# ---------------------------------------------------------------------------


class ComparableSaleResponse(BaseModel):
    """A single comparable land sale."""

    address: str = ""
    sale_price: float = 0.0
    sale_date: str = ""
    lot_size_sqft: float = 0.0
    zoning_code: str = ""
    distance_miles: float = 0.0
    price_per_acre: float = 0.0
    price_per_unit: float | None = None
    adjustments: dict[str, float] = {}


class CompAnalysisResponse(BaseModel):
    """Comparable sales analysis results."""

    comparables: list[ComparableSaleResponse] = []
    median_price_per_acre: float = 0.0
    estimated_land_value: float = 0.0
    adv_per_unit: float | None = None
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Land Pro Forma — Residual Valuation (Phase 6B)
# ---------------------------------------------------------------------------


class LandProFormaResponse(BaseModel):
    """Residual land valuation pro forma."""

    gross_development_value: float = 0.0
    hard_costs: float = 0.0
    soft_costs: float = 0.0
    builder_margin: float = 0.0
    max_land_price: float = 0.0
    cost_per_door: float = 0.0
    construction_cost_psf: float = 175.0
    avg_unit_size_sqft: float = 1000.0
    adv_per_unit: float = 0.0
    max_units: int = 0
    soft_cost_pct: float = 20.0
    builder_margin_pct: float = 25.0
    notes: list[str] = []


class ErrorResponse(BaseModel):
    """Error response body."""

    detail: str
    error_type: str = "pipeline_error"


# ---------------------------------------------------------------------------
# Document Generation (Clause Builder)
# ---------------------------------------------------------------------------


class DocumentGenerateRequest(BaseModel):
    """Request body for POST /api/v1/documents/generate and /preview."""

    document_type: str = Field(
        ...,
        description="Document type: loi, psa, deal_summary, proforma_spreadsheet",
    )
    deal_type: str = Field(
        default="land_deal",
        description="Deal type: land_deal, subject_to, wrap, hybrid, seller_finance, wholesale",
    )
    context: dict = Field(
        default_factory=dict,
        description="Deal context fields (property_address, buyer_name, etc.)",
    )
    output_format: str | None = Field(
        default=None,
        description="Output format override: docx, xlsx. Auto-detected if omitted.",
    )


class DocumentPreviewResponse(BaseModel):
    """Preview of rendered clauses without generating a file."""

    document_type: str
    deal_type: str
    clause_count: int
    clauses: list[dict] = []


class DocumentTemplateInfo(BaseModel):
    """Metadata about an available document template."""

    document_type: str
    label: str
    description: str
    supported_deal_types: list[str] = []
    supported_formats: list[str] = []
    required_fields: list[str] = []
    optional_fields: list[str] = []


# ---------------------------------------------------------------------------
# Chat (Phase 5c)
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single message in a conversation."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    """Request body for POST /api/v1/chat."""

    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = []
    report_context: ZoningReportResponse | None = None
    session_id: str | None = None


# ---------------------------------------------------------------------------
# Portfolio (Phase 5b)
# ---------------------------------------------------------------------------


class SaveAnalysisRequest(BaseModel):
    """Request to save an analysis to portfolio."""

    report: ZoningReportResponse


class SavedAnalysisResponse(BaseModel):
    """A saved analysis in the portfolio."""

    id: str
    address: str
    municipality: str
    county: str
    zoning_district: str
    max_units: int | None = None
    confidence: str = ""
    saved_at: str
    report: ZoningReportResponse


# ---------------------------------------------------------------------------
# Geometry / Buildable Envelope (Sprint 3)
# ---------------------------------------------------------------------------


class EnvelopeRequest(BaseModel):
    """Request for buildable envelope geometry computation."""

    lot_width_ft: float = Field(..., gt=0, description="Lot width in feet")
    lot_depth_ft: float = Field(..., gt=0, description="Lot depth in feet")
    setback_front_ft: float = Field(default=0, ge=0)
    setback_side_ft: float = Field(default=0, ge=0)
    setback_rear_ft: float = Field(default=0, ge=0)
    max_height_ft: float = Field(default=35.0, gt=0)
    max_stories: int | None = None
    floor_area_ratio: float | None = Field(default=None, gt=0)
    lot_coverage_pct: float | None = Field(default=None, gt=0, le=100)


class EnvelopeVertex(BaseModel):
    """A 3D point."""

    x: float
    y: float
    z: float


class EnvelopeGeometry(BaseModel):
    """Computed buildable envelope geometry for 3D visualization."""

    # Lot outline (ground plane, z=0)
    lot_polygon: list[EnvelopeVertex]
    lot_area_sqft: float

    # Setback lines (ground plane)
    setback_polygon: list[EnvelopeVertex]

    # Buildable envelope (3D box)
    buildable_footprint_sqft: float
    buildable_volume_cuft: float
    buildable_width_ft: float
    buildable_depth_ft: float
    max_height_ft: float

    # Constraints applied
    effective_height_ft: float
    effective_coverage_pct: float
    far_limited: bool = False
    coverage_limited: bool = False

    # Metadata
    notes: list[str] = []


# ---------------------------------------------------------------------------
# Floor Plan (Sprint 3)
# ---------------------------------------------------------------------------


class FloorPlanUnitResponse(BaseModel):
    """A single unit in the floor plan."""

    unit_id: str
    area_sqft: float
    width_ft: float
    depth_ft: float
    floor: int
    label: str


class FloorPlanRequest(BaseModel):
    """Request for parametric floor plan generation."""

    buildable_width_ft: float = Field(..., gt=0)
    buildable_depth_ft: float = Field(..., gt=0)
    max_height_ft: float = Field(default=35.0, gt=0)
    max_units: int = Field(default=1, ge=1)
    min_unit_size_sqft: float = Field(default=400.0, gt=0)
    parking_per_unit: float = Field(default=1.5, ge=0)
    story_height_ft: float = Field(default=10.0, gt=0)
    template: str = Field(default="auto")


class FloorPlanResponse(BaseModel):
    """Generated floor plan result."""

    template: str
    units: list[FloorPlanUnitResponse]
    total_units: int
    buildable_width_ft: float
    buildable_depth_ft: float
    max_height_ft: float
    stories: int
    parking_spaces: int = 0
    notes: list[str] = []
    svg: str = ""


# ---------------------------------------------------------------------------
# Pro Forma (Phase F3)
# ---------------------------------------------------------------------------


class PropertyTypeProFormaResponse(BaseModel):
    """Property-type-specific pro forma summary embedded in zoning report."""

    property_type: str  # "land" | "single_family" | "multifamily" | "commercial_mf"
    label: str  # Human-readable label
    metrics: dict = {}  # Key financial metrics for this property type
    notes: list[str] = []


class ProFormaRequest(BaseModel):
    """Request for pro forma generation."""

    address: str = ""
    municipality: str = ""
    county: str = ""
    zoning_district: str = ""
    lot_size_sqft: float = Field(default=0.0, ge=0)
    max_units: int = Field(default=1, ge=1)
    unit_size_sqft: float = Field(default=1000.0, gt=0)
    stories: int = Field(default=1, ge=1)
    parking_spaces: int = Field(default=2, ge=0)
    land_cost: float = Field(default=0.0, ge=0)
    construction_cost_psf: float = Field(default=150.0, gt=0)
    soft_cost_pct: float = Field(default=15.0, ge=0)
    contingency_pct: float = Field(default=10.0, ge=0)
    ltv_pct: float = Field(default=75.0, ge=0, le=100)
    interest_rate_pct: float = Field(default=7.0, ge=0)
    loan_term_years: int = Field(default=30, ge=1)
    monthly_rent_per_unit: float = Field(default=0.0, ge=0)
    sale_price_per_unit: float = Field(default=0.0, ge=0)
    vacancy_pct: float = Field(default=5.0, ge=0, le=100)
    operating_expense_pct: float = Field(default=35.0, ge=0, le=100)
    narrative: str = ""


class ProFormaResponse(BaseModel):
    """Computed pro forma results."""

    total_buildable_sqft: float
    hard_costs: float
    soft_costs: float
    contingency: float
    total_development_cost: float
    loan_amount: float
    equity_required: float
    annual_debt_service: float
    gross_annual_income: float
    effective_gross_income: float
    operating_expenses: float
    net_operating_income: float
    cap_rate_pct: float
    cash_on_cash_pct: float
    total_sale_revenue: float
    total_profit: float
    roi_pct: float
    notes: list[str] = []
