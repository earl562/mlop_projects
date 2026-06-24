"""Domain types for the plotlot zoning analysis platform.

All shared dataclasses and type definitions live here to prevent
circular imports and establish a single source of truth for the
domain model. Every other module imports from here.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plotlot.core.lookup_snapshot import LookupSnapshot


# ---------------------------------------------------------------------------
# Municode API types
# ---------------------------------------------------------------------------


@dataclass
class MunicodeConfig:
    """Municode API identifiers for a municipality's zoning code."""

    municipality: str
    county: str
    client_id: int
    product_id: int
    job_id: int
    zoning_node_id: str
    state: str = "FL"  # Two-letter state code (FL, NC, etc.)


@dataclass
class RawSection:
    """A raw section of ordinance text scraped from Municode."""

    municipality: str
    county: str
    node_id: str
    heading: str
    parent_heading: str | None
    html_content: str
    depth: int


@dataclass
class TocNode:
    """A node in the Municode table-of-contents tree."""

    node_id: str
    heading: str
    has_children: bool
    depth: int
    parent_heading: str | None = None
    children: list["TocNode"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Chunk types
# ---------------------------------------------------------------------------


@dataclass
class ChunkMetadata:
    """Metadata attached to each text chunk for filtering and retrieval."""

    municipality: str
    county: str
    chapter: str
    section: str
    section_title: str
    zone_codes: list[str]
    chunk_index: int
    municode_node_id: str


@dataclass
class TextChunk:
    """A text chunk ready for embedding, with its metadata."""

    text: str
    metadata: ChunkMetadata


# ---------------------------------------------------------------------------
# Search types
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """A single result from hybrid search."""

    section: str
    section_title: str
    zone_codes: list[str]
    chunk_text: str
    score: float
    municipality: str
    chunk_id: int | None = None
    chapter: str | None = None
    municode_node_id: str | None = None
    source_url: str | None = None


# ---------------------------------------------------------------------------
# Fallback configs — verified against live Municode API.
# Used when Library API discovery is unavailable.
# ---------------------------------------------------------------------------

_FALLBACK_CONFIGS: dict[str, MunicodeConfig] = {
    "miami_dade": MunicodeConfig(
        municipality="Unincorporated Miami-Dade",
        county="miami_dade",
        client_id=11719,
        product_id=10620,
        job_id=483425,
        zoning_node_id="PTIIICOOR_CH33ZO",
    ),
    # Fort Lauderdale: zoning spans 15 ULADRE articles at root level;
    # empty string = walk entire root TOC (correct and intentional).
    "fort_lauderdale": MunicodeConfig(
        municipality="Fort Lauderdale",
        county="broward",
        client_id=2247,
        product_id=13463,
        job_id=482747,
        zoning_node_id="",
    ),
    "davie": MunicodeConfig(
        municipality="Davie",
        county="broward",
        client_id=8419,
        product_id=10630,
        job_id=484015,
        zoning_node_id="PTIICOOR_CH12LADECO",
    ),
    "miami_gardens": MunicodeConfig(
        municipality="Miami Gardens",
        county="miami_dade",
        client_id=13114,
        product_id=14432,
        job_id=481139,
        zoning_node_id="SPBLADECO",
    ),
    # West Palm Beach: Ch94 ZONING AND LAND DEVELOPMENT is a root-level leaf
    # (HasChildren=False). Empty string walks root TOC and finds it naturally.
    "west_palm_beach": MunicodeConfig(
        municipality="West Palm Beach",
        county="palm_beach",
        client_id=4897,
        product_id=10017,
        job_id=480641,
        zoning_node_id="",
    ),
    "miramar": MunicodeConfig(
        municipality="Miramar",
        county="broward",
        client_id=3289,
        product_id=13202,
        job_id=479943,
        zoning_node_id="APXAFESC",
    ),
    # Boynton Beach: LAND DEVELOPMENT REGULATIONS (LADERE) is a root-level leaf
    # (HasChildren=False). Empty string walks root TOC and finds it naturally.
    "boynton_beach": MunicodeConfig(
        municipality="Boynton Beach",
        county="palm_beach",
        client_id=1369,
        product_id=12672,
        job_id=492855,
        zoning_node_id="",
    ),
    "miami_springs": MunicodeConfig(
        municipality="Miami Springs",
        county="miami_dade",
        client_id=3290,
        product_id=13202,
        job_id=463573,
        zoning_node_id="TITXVLAUS_CH150ZOCO",
    ),
    "opa_locka": MunicodeConfig(
        municipality="Opa Locka",
        county="miami_dade",
        client_id=3696,
        product_id=11375,
        job_id=475408,
        zoning_node_id="CIOCKFLLADERE",
    ),
    # South Miami: Code of Ordinances product (11587) has Ch20 ZONING (RESERVED).
    # Switched to Land Development Code product (12667) which has 10 root-level
    # articles (I–XII), all land-development related.
    "south_miami": MunicodeConfig(
        municipality="South Miami",
        county="miami_dade",
        client_id=4404,
        product_id=12667,
        job_id=469340,
        zoning_node_id="",
    ),
    # Wellington: Code of Ordinances product (13115) has no zoning chapter.
    # Switched to Unified Land Development Code product (14703) with 8 root-level
    # articles (1–9), all land-development related.
    "wellington": MunicodeConfig(
        municipality="Wellington",
        county="palm_beach",
        client_id=10940,
        product_id=14703,
        job_id=476382,
        zoning_node_id="",
    ),
}

MUNICODE_CONFIGS = _FALLBACK_CONFIGS


# ---------------------------------------------------------------------------
# NC Charlotte Metro fallback configs — verified against live Municode API.
# stateId=34 for North Carolina.
# ---------------------------------------------------------------------------

_NC_FALLBACK_CONFIGS: dict[str, MunicodeConfig] = {
    "charlotte": MunicodeConfig(
        municipality="Charlotte",
        county="mecklenburg",
        client_id=19970,
        product_id=14045,
        job_id=489001,
        zoning_node_id="APXAZOORDS",
        state="NC",
    ),
    "huntersville": MunicodeConfig(
        municipality="Huntersville",
        county="mecklenburg",
        client_id=7619,
        product_id=14072,
        job_id=488501,
        zoning_node_id="PTIICOOR_ART9ZO",
        state="NC",
    ),
    "cornelius": MunicodeConfig(
        municipality="Cornelius",
        county="mecklenburg",
        client_id=7478,
        product_id=14029,
        job_id=487201,
        zoning_node_id="PTIICOOR_CH18LADERE",
        state="NC",
    ),
    "davidson": MunicodeConfig(
        municipality="Davidson",
        county="mecklenburg",
        client_id=7479,
        product_id=14030,
        job_id=487301,
        zoning_node_id="PTIICOOR_CH10PLZO",
        state="NC",
    ),
    "matthews": MunicodeConfig(
        municipality="Matthews",
        county="mecklenburg",
        client_id=7540,
        product_id=14091,
        job_id=487401,
        zoning_node_id="APXALAMUZO",
        state="NC",
    ),
    "mint_hill": MunicodeConfig(
        municipality="Mint Hill",
        county="mecklenburg",
        client_id=7547,
        product_id=14096,
        job_id=487501,
        zoning_node_id="PTIICOOR_CH14ZO",
        state="NC",
    ),
    "pineville": MunicodeConfig(
        municipality="Pineville",
        county="mecklenburg",
        client_id=7577,
        product_id=14116,
        job_id=487601,
        zoning_node_id="APXALAMUZO",
        state="NC",
    ),
    "concord": MunicodeConfig(
        municipality="Concord",
        county="cabarrus",
        client_id=7475,
        product_id=14027,
        job_id=487701,
        zoning_node_id="PTIICOOR_CH22ZO",
        state="NC",
    ),
    "kannapolis": MunicodeConfig(
        municipality="Kannapolis",
        county="cabarrus",
        client_id=7527,
        product_id=14083,
        job_id=487801,
        zoning_node_id="APXALAMUZO",
        state="NC",
    ),
    "mooresville": MunicodeConfig(
        municipality="Mooresville",
        county="iredell",
        client_id=7552,
        product_id=14100,
        job_id=487901,
        zoning_node_id="PTIICOOR_CH20ZO",
        state="NC",
    ),
    "monroe": MunicodeConfig(
        municipality="Monroe",
        county="union",
        client_id=7549,
        product_id=14098,
        job_id=488001,
        zoning_node_id="APXALAMUZO",
        state="NC",
    ),
    "waxhaw": MunicodeConfig(
        municipality="Waxhaw",
        county="union",
        client_id=7639,
        product_id=14154,
        job_id=488101,
        zoning_node_id="PTIICOOR_CH18ZO",
        state="NC",
    ),
}

NC_MUNICODE_CONFIGS = _NC_FALLBACK_CONFIGS


# ---------------------------------------------------------------------------
# CA static overrides — municipalities where auto-discovery picks the wrong
# product (e.g. Oakland has a separate "Planning Code" product that must be
# used instead of its "Code of Ordinances").
# ---------------------------------------------------------------------------

_CA_OVERRIDES: dict[str, MunicodeConfig] = {
    "oakland_ca": MunicodeConfig(
        municipality="Oakland",
        county="Alameda",
        client_id=3637,
        product_id=16490,
        job_id=481576,
        zoning_node_id="",  # chapters are root-level siblings; empty string → no nodeId param
        state="CA",
    ),
}

CA_OVERRIDES = _CA_OVERRIDES


# ---------------------------------------------------------------------------
# Property record from county Property Appraiser
# ---------------------------------------------------------------------------


@dataclass
class PropertyRecord:
    """Property data from county Property Appraiser ArcGIS API.

    Populated by querying the county's open ArcGIS REST services.
    Fields vary by county — empty string means not available.
    """

    # Identifiers
    folio: str = ""
    address: str = ""
    municipality: str = ""
    county: str = ""

    # Owner
    owner: str = ""

    # Zoning (from spatial zoning layer)
    zoning_code: str = ""  # e.g., "R-1", "RS-4", "BU-2"
    zoning_description: str = ""

    # Land use (from property record)
    land_use_code: str = ""  # e.g., "0100", "0101"
    land_use_description: str = ""

    # Lot
    lot_size_sqft: float = 0.0
    lot_dimensions: str = ""  # e.g., "75 x 100" from legal description
    lot_size_source: str = ""  # "assessor", "geometry", or "" — provenance of the lot area

    # Building
    bedrooms: int = 0
    bathrooms: float = 0.0
    half_baths: int = 0
    floors: int = 0
    living_units: int = 0
    building_area_sqft: float = 0.0
    living_area_sqft: float = 0.0
    year_built: int = 0

    # Valuation
    assessed_value: float = 0.0
    market_value: float = 0.0
    last_sale_price: float = 0.0
    last_sale_date: str = ""

    # Location
    lat: float | None = None
    lng: float | None = None

    # Parcel boundary polygon — [[lng, lat], ...] in WGS84
    parcel_geometry: list[list[float]] | None = None

    # Dynamic zoning layer URL (discovered via ArcGIS Hub)
    zoning_layer_url: str = ""


# ---------------------------------------------------------------------------
# Numeric zoning parameters (extracted by LLM for calculation)
# ---------------------------------------------------------------------------


@dataclass
class NumericZoningParams:
    """Numeric values extracted by LLM from ordinance text. None = not found."""

    max_density_units_per_acre: float | None = None  # e.g., 6.0
    min_lot_area_per_unit_sqft: float | None = None  # e.g., 7500.0
    far: float | None = None  # e.g., 0.50
    max_lot_coverage_pct: float | None = None  # e.g., 40.0
    max_height_ft: float | None = None  # e.g., 35.0
    max_stories: int | None = None  # e.g., 2
    setback_front_ft: float | None = None
    setback_side_ft: float | None = None
    setback_rear_ft: float | None = None
    min_unit_size_sqft: float | None = None  # e.g., 750.0
    min_lot_width_ft: float | None = None  # e.g., 75.0
    parking_spaces_per_unit: float | None = None  # e.g., 2.0
    parking_per_1000_gla_sqft: float | None = None  # e.g., 4.0
    max_gla_sqft: float | None = None  # total allowable GLA
    min_tenant_size_sqft: float | None = None  # min individual tenant space
    loading_spaces: int | None = None  # loading docks required
    property_type: str | None = (
        None  # "land" | "single_family" | "multifamily" | "commercial_mf" | "commercial"
    )
    provenance: str = ""


@dataclass
class ConstraintResult:
    """One constraint's contribution to the max-units calculation."""

    name: str  # "density", "min_lot_area", "floor_area_ratio", "buildable_envelope"
    max_units: int  # floor() of calculated max
    raw_value: float  # unrounded
    formula: str  # human-readable, e.g., "7500 sqft / 7500 sqft/unit = 1.0"
    is_governing: bool = False


@dataclass
class DensityAnalysis:
    """Max allowable units on a lot, with full constraint breakdown."""

    max_units: int
    governing_constraint: str
    constraints: list[ConstraintResult]
    lot_size_sqft: float = 0.0
    buildable_area_sqft: float | None = None
    lot_width_ft: float | None = None
    lot_depth_ft: float | None = None
    max_gla_sqft: float | None = None  # commercial: max gross leasable area
    confidence: str = "low"
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Zoning analysis output
# ---------------------------------------------------------------------------


@dataclass
class Setbacks:
    """Building setback requirements in feet."""

    front: str = ""
    side: str = ""
    rear: str = ""


@dataclass
class SourceRef:
    """A reference to a source ordinance chunk backing an extracted value.

    Links extracted zoning parameters back to the specific ordinance text
    they came from — enables inline citations in the frontend (Perplexity-style).
    """

    section: str = ""
    section_title: str = ""
    chunk_text_preview: str = ""  # First 200 chars of the source chunk
    score: float = 0.0


@dataclass
class ZoningReport:
    """Structured zoning analysis for a property address.

    This is the primary output of the full lookup pipeline:
    address → geocode → search → LLM analysis → ZoningReport.
    """

    address: str
    formatted_address: str
    municipality: str
    county: str
    lat: float | None = None
    lng: float | None = None

    # Zoning classification
    zoning_district: str = ""
    zoning_description: str = ""

    # Land use
    allowed_uses: list[str] = field(default_factory=list)
    conditional_uses: list[str] = field(default_factory=list)
    prohibited_uses: list[str] = field(default_factory=list)

    # Dimensional standards
    setbacks: Setbacks = field(default_factory=Setbacks)
    max_height: str = ""
    max_density: str = ""
    floor_area_ratio: str = ""
    lot_coverage: str = ""
    min_lot_size: str = ""

    # Parking
    parking_requirements: str = ""

    # Property record (from county PA)
    property_record: PropertyRecord | None = None

    # Numeric params + max units calculation
    numeric_params: NumericZoningParams | None = None
    density_analysis: DensityAnalysis | None = None

    # Comparable sales + pro forma
    comp_analysis: "CompAnalysis | None" = None
    pro_forma: "LandProForma | None" = None

    # Deal analysis (Dani Kleyman underwriting framework)
    deal_analysis: "DealAnalysis | None" = None

    # Summary
    summary: str = ""
    sources: list[str] = field(default_factory=list)
    confidence: str = ""  # "high", "medium", "low"

    # Inline citations — maps extracted values back to source ordinance chunks
    source_refs: list[SourceRef] = field(default_factory=list)

    validation_warnings: list[str] = field(default_factory=list)

    # Site risk — FEMA flood zone + NWI wetland data
    site_risk: "SiteRisk | None" = None
    lookup_snapshot: "LookupSnapshot | None" = None


# ---------------------------------------------------------------------------
# Site risk types
# ---------------------------------------------------------------------------


@dataclass
class FloodZoneInfo:
    """FEMA flood zone designation for a parcel."""

    zone: str  # e.g. "AE", "X", "VE"
    zone_subtype: str  # FEMA ZONE_SUBTY field
    in_sfha: bool  # Special Flood Hazard Area — mandatory flood insurance
    risk_level: str  # "high", "moderate", "minimal", "undetermined"
    description: str


@dataclass
class WetlandInfo:
    """A single NWI wetland polygon intersecting or adjacent to the parcel."""

    wetland_type: str  # e.g. "Freshwater Emergent Wetland"
    acres: float


@dataclass
class GeologicHazard:
    """CGS seismic/geologic hazard designations for a parcel.

    Retrieved from the CA statewide parcel layer (FaultZone, LandslideZone,
    LiquefactionZone fields with CGS coded-value legends).
    """

    fault_zone_status: str = ""  # e.g. "not in fault zone", "in fault zone", "not evaluated"
    landslide_status: str = ""
    liquefaction_status: str = ""
    source: str = ""  # e.g. "CA_State_Parcels CGS fields"


@dataclass
class PermitRecord:
    """A single building/development permit from the city's permitting system.

    Retrieved from the City of San Diego DSDPermits Accela layer.
    """

    permit_holder: str = ""
    permit_type: str = ""
    permit_status: str = ""
    issue_date: str = ""
    project_title: str = ""
    approval_url: str = ""


@dataclass
class SiteRisk:
    """Physical site risk flags drawn from FEMA NFHL, USFWS NWI, and CGS hazard data."""

    flood_zone: FloodZoneInfo | None = None
    wetlands: list[WetlandInfo] = field(default_factory=list)
    has_wetlands: bool = False
    geologic_hazard: GeologicHazard | None = None
    overall_risk: str = "unknown"  # "high", "moderate", "low", "unknown"
    risk_flags: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Comparable sales types
# ---------------------------------------------------------------------------


@dataclass
class ComparableSale:
    """A single comparable land sale from county property appraiser data."""

    address: str = ""
    sale_price: float = 0.0
    sale_date: str = ""
    lot_size_sqft: float = 0.0
    zoning_code: str = ""
    distance_miles: float = 0.0
    price_per_acre: float = 0.0
    price_per_unit: float | None = None
    adjustments: dict[str, float] = field(default_factory=dict)


@dataclass
class CompAnalysis:
    """Comparable sales analysis results."""

    comparables: list[ComparableSale] = field(default_factory=list)
    median_price_per_acre: float = 0.0
    estimated_land_value: float = 0.0

    # Price range across the land comps (25th / 75th percentile of $/acre and
    # the resulting land-value band for the subject). Gives users a sense of
    # the pricing spread within the search radius, not just a single point.
    price_per_acre_low: float = 0.0
    price_per_acre_high: float = 0.0
    estimated_land_value_low: float = 0.0
    estimated_land_value_high: float = 0.0

    # After-development value derived from nearby improved (finished) sales.
    adv_per_unit: float | None = None
    adv_per_unit_low: float | None = None
    adv_per_unit_high: float | None = None
    adv_source: str = ""  # "comps" | "" (empty when no improved sales found)
    # Exit comps — improved/finished sales used to derive ADV per unit.
    unit_comparables: list[ComparableSale] = field(default_factory=list)

    confidence: float = 0.0  # 0.0-1.0 based on comp count and recency
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Land deal pro forma (residual land valuation)
# ---------------------------------------------------------------------------


@dataclass
class LandProForma:
    """Residual land valuation for land deal intelligence.

    GDV = Max Units × ADV per Unit
    Max Land Price = (GDV × (1 − sweat_equity%)) − Hard − Soft − Financing
    """

    gross_development_value: float = 0.0
    hard_costs: float = 0.0
    soft_costs: float = 0.0
    builder_margin: float = 0.0
    sweat_equity: float = 0.0
    financing_costs: float = 0.0
    max_land_price: float = 0.0
    cost_per_door: float = 0.0
    construction_cost_psf: float = 200.0
    avg_unit_size_sqft: float = 1000.0
    adv_per_unit: float = 0.0
    max_units: int = 0
    soft_cost_pct: float = 20.0
    builder_margin_pct: float = 25.0
    # Provenance of the ADV used: "comps" (from sold-unit comps),
    # "regional_default" (market fallback), "override" (caller-supplied),
    # or "comps_land_value" (last-resort land-value fallback).
    adv_source: str = ""
    market: str = ""  # regional cost-model label, e.g. "San Diego"
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 6 — Data Center Site Selection
# ---------------------------------------------------------------------------


@dataclass
class DataCenterParams:
    """Zoning and physical parameters extracted for data center siting.

    Separate from NumericZoningParams — data centers care about industrial
    setbacks, noise limits, utility easements, and outdoor equipment areas,
    not residential density math.
    """

    # Industrial zoning
    zoning_code: str = ""
    zoning_description: str = ""
    is_industrial_permitted: bool | None = None  # True if I/M/BL district allows data centers
    conditional_use_required: bool | None = None  # True if CUP/SUP needed

    # Dimensional standards (industrial)
    setback_front_ft: float | None = None
    setback_side_ft: float | None = None
    setback_rear_ft: float | None = None
    max_height_ft: float | None = None
    max_lot_coverage_pct: float | None = None
    max_far: float | None = None

    # Operational standards
    noise_limit_db: float | None = None  # dB(A) at property line
    outdoor_equipment_allowed: bool | None = None  # cooling towers, generators
    min_lot_area_sqft: float | None = None
    loading_docks_required: int | None = None

    # Utility easements / special requirements
    utility_easement_notes: str = ""
    source_sections: list[str] = field(default_factory=list)


@dataclass
class InfraSignal:
    """A single infrastructure signal (power, fiber, flood, seismic, zoning).

    score: 0.0–1.0 (1.0 = best). Used to compute composite SiteScorecard.
    """

    name: str  # "power_grid" | "fiber" | "flood_zone" | "seismic" | "zoning"
    label: str  # Human label, e.g., "Grid Capacity"
    score: float  # 0.0–1.0
    rating: str  # "Excellent" | "Good" | "Fair" | "Poor"
    summary: str  # 1-2 sentence plain-language explanation
    raw_value: str  # raw API value, e.g., "Zone X" or "1 Gbps fiber"
    source: str  # API source, e.g., "EIA API" | "FCC NBM" | "FEMA NFIP"
    confidence: str = "high"  # "high" | "medium" | "low"


@dataclass
class SiteScorecard:
    """Data center site selection scorecard.

    Composite score across 5 infrastructure signals. Each signal
    contributes 20% to the composite (equal weighting for v1).
    """

    address: str
    formatted_address: str
    municipality: str
    county: str
    lat: float | None = None
    lng: float | None = None

    # Property
    property_record: PropertyRecord | None = None

    # Infrastructure signals
    power_signal: InfraSignal | None = None
    fiber_signal: InfraSignal | None = None
    flood_signal: InfraSignal | None = None
    seismic_signal: InfraSignal | None = None
    zoning_signal: InfraSignal | None = None

    # Extracted zoning params (industrial)
    datacenter_params: DataCenterParams | None = None

    # Composite score
    composite_score: float = 0.0  # 0.0–1.0 weighted average of signals
    composite_rating: str = ""  # "Excellent" | "Good" | "Fair" | "Poor" | "Disqualified"

    # Executive summary
    summary: str = ""
    deal_breakers: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    confidence: str = "medium"


# ============================================================================
# Deal Analysis types — Dani Kleyman Underwriting Framework
# ============================================================================


@dataclass
class UnitMixEntry:
    unit_type: str = ""
    bedrooms: int = 0
    bathrooms: float = 0.0
    sqft: float = 0.0
    unit_count: int = 0
    percentage_of_total: float = 0.0
    monthly_rent: float = 0.0
    annual_rent: float = 0.0
    rent_per_sqft: float = 0.0


@dataclass
class RentalComp:
    property_name: str = ""
    address: str = ""
    bedrooms: int = 0
    bathrooms: float = 0.0
    sqft: float = 0.0
    monthly_rent: float = 0.0
    rent_per_sqft: float = 0.0
    unit_type: str = ""
    source: str = ""
    last_updated: str = ""


@dataclass
class RentalCompSet:
    comps: list[RentalComp] = field(default_factory=list)
    comp_count: int = 0
    median_rent: float = 0.0
    median_rent_per_sqft: float = 0.0
    avg_rent: float = 0.0
    avg_rent_per_sqft: float = 0.0
    avg_sqft: float = 0.0
    rent_range_low: float = 0.0
    rent_range_high: float = 0.0
    source: str = ""
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class ProformaNOI:
    unit_mix: list[UnitMixEntry] = field(default_factory=list)
    total_units: int = 0
    gross_monthly_income: float = 0.0
    gross_annual_income: float = 0.0
    vacancy_rate_pct: float = 5.0
    effective_gross_income: float = 0.0
    operating_expense_ratio_pct: float = 35.0
    operating_expenses: float = 0.0
    net_operating_income: float = 0.0
    monthly_noi: float = 0.0
    expense_items: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class FinancingTerms:
    loan_type: str = "construction-to-permanent"
    lender: str = ""
    loan_to_cost: float = 70.0
    interest_rate: float = 6.5
    rate_type: str = "fixed"
    amortization_years: int = 30
    min_dscr: float = 1.25
    origination_fee_pct: float = 1.0
    developer_fee_pct: float = 8.0
    other_closing_costs_pct: float = 0.5
    construction_loan_ltc: float = 70.0
    construction_loan_rate: float = 7.0
    construction_months: float = 14.0
    permanent_loan_rate: float = 6.5
    permanent_loan_amort_years: int = 30
    notes: list[str] = field(default_factory=list)


@dataclass
class CapitalStack:
    total_project_cost: float = 0.0
    land_cost: float = 0.0
    hard_costs: float = 0.0
    soft_costs: float = 0.0
    developer_fee: float = 0.0
    financing_costs: float = 0.0
    interest_carry: float = 0.0
    max_construction_loan: float = 0.0
    max_permanent_loan: float = 0.0
    senior_debt: float = 0.0
    senior_debt_pct: float = 0.0
    mezzanine_debt: float = 0.0
    mezzanine_debt_pct: float = 0.0
    preferred_equity: float = 0.0
    preferred_equity_pct: float = 0.0
    total_debt: float = 0.0
    sponsor_equity: float = 0.0
    sponsor_equity_pct: float = 0.0
    investor_equity: float = 0.0
    total_equity: float = 0.0
    equity_required: float = 0.0
    ltc_pct: float = 0.0
    ltv_pct: float = 0.0
    weighted_cost_of_debt: float = 0.0
    weighted_cost_of_equity: float = 0.0
    weighted_avg_cost_of_capital: float = 0.0
    senior_terms: "FinancingTerms | None" = None
    mezz_terms: "FinancingTerms | None" = None
    notes: list[str] = field(default_factory=list)


@dataclass
class DealMetrics:
    levered_irr: float = 0.0
    levered_equity_multiple: float = 0.0
    levered_cash_on_cash: float = 0.0
    unlevered_irr: float = 0.0
    unlevered_equity_multiple: float = 0.0
    cap_rate: float = 0.0
    yield_on_cost: float = 0.0
    debt_yield: float = 0.0
    dscr: float = 0.0
    gross_profit: float = 0.0
    net_present_value: float = 0.0
    payback_period_years: float = 0.0
    break_even_occupancy_pct: float = 0.0
    sensitivity_notes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class DataSufficiency:
    """Gate that assesses whether the pipeline has enough data to produce a
    reliable investment verdict.

    Grade is one of ``"sufficient"`` (all required sources present),
    ``"partial"`` (some gaps but analysis can proceed with caveats), or
    ``"insufficient"`` (critical data missing — verdict must be withheld).
    """

    grade: str  # "sufficient" | "partial" | "insufficient"
    reason: str  # human-readable explanation of what is missing
    sources_checked: list[str] = field(default_factory=list)


@dataclass
class DealAnalysis:
    address: str = ""
    municipality: str = ""
    county: str = ""
    property_type: str = ""
    max_units: int = 0
    estimated_land_value: float = 0.0
    estimated_land_value_per_unit: float = 0.0
    estimated_land_value_per_acre: float = 0.0
    comp_analysis: "CompAnalysis | None" = None
    pro_forma: "LandProForma | None" = None
    proforma_noi: "ProformaNOI | None" = None
    rental_comp_set: "RentalCompSet | None" = None
    unit_mix: list[UnitMixEntry] = field(default_factory=list)
    financing_terms: "FinancingTerms | None" = None
    capital_stack: "CapitalStack | None" = None
    metrics: "DealMetrics | None" = None
    max_offer_price: float = 0.0
    recommended_offer: float = 0.0
    assignment_fee: float = 0.0
    max_offer_to_seller: float = 0.0
    user_mode: str = "builder"
    investment_rating: str = ""
    data_sufficiency: "DataSufficiency | None" = None
    deal_breakers: list[str] = field(default_factory=list)
    summary: str = ""
    notes: list[str] = field(default_factory=list)
    confidence: str = "medium"

    last_sale_price: float = 0.0
    last_sale_date: str = ""


# ---------------------------------------------------------------------------
# Infill lot analysis — Path 1: spec house / for-sale
# ---------------------------------------------------------------------------


@dataclass
class InfillLotAnalysis:
    """Path 1 valuation result for a spec house or infill lot (≤1 unit, for-sale).

    Formula: Max Land = ARV × (1 − profit%) − Build Cost − (ARV × closing%)

    All parameters sourced from ``RegionalCostModel`` (market-specific).
    Negative ``max_land_value`` is allowed — it signals "don't build."
    The calling code clamps to 0 and sets a flag; do NOT clamp here.
    """

    arv: float  # After-Repair (as-built) value
    build_cost: float  # Hard construction cost ($)
    profit_margin: float  # Builder profit ($)
    closing_costs: float  # Sale closing costs ($)
    max_land_value: float  # Residual land value ($)
    exit_strategy: str = "for_sale"
    market: str = ""
    assignment_fee: float = 0.0
    max_offer_to_seller: float = 0.0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Enum types
# ---------------------------------------------------------------------------


class AnalysisRunStatus(StrEnum):
    """Lifecycle states for an AnalysisRun.

    Additive over existing raw strings — ``StrEnum`` members ARE strings,
    so existing comparisons like ``run.status == "pending"`` still work.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
