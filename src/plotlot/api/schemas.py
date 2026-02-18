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
