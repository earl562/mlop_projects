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
        description="South Florida property address (Miami-Dade, Broward, or Palm Beach County)",
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


class DensityAnalysisResponse(BaseModel):
    max_units: int
    governing_constraint: str
    constraints: list[ConstraintResponse]
    lot_size_sqft: float = 0.0
    buildable_area_sqft: float | None = None
    lot_width_ft: float | None = None
    lot_depth_ft: float | None = None
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
    density_analysis: DensityAnalysisResponse | None = None

    summary: str = ""
    sources: list[str] = []
    confidence: str = ""

    # Progressive autonomy metadata (Klarna confidence-gated pattern)
    confidence_warning: str = ""
    suggested_next_steps: list[str] = []


class ErrorResponse(BaseModel):
    """Error response body."""

    detail: str
    error_type: str = "pipeline_error"


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
