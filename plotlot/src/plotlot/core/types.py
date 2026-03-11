"""Domain types for the plotlot zoning analysis platform.

All shared dataclasses and type definitions live here to prevent
circular imports and establish a single source of truth for the
domain model. Every other module imports from here.
"""

from dataclasses import dataclass, field


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
    "fort_lauderdale": MunicodeConfig(
        municipality="Fort Lauderdale",
        county="broward",
        client_id=2247,
        product_id=13463,
        job_id=482747,
        zoning_node_id="UNLADERE_CH47UNLADERE_ARTIIZODIRE",
    ),
    "miami_gardens": MunicodeConfig(
        municipality="Miami Gardens",
        county="miami_dade",
        client_id=13114,
        product_id=14432,
        job_id=481139,
        zoning_node_id="SPBLADECO",
    ),
    "west_palm_beach": MunicodeConfig(
        municipality="West Palm Beach",
        county="palm_beach",
        client_id=4897,
        product_id=10017,
        job_id=480641,
        zoning_node_id="PTIICOOR_CH94ZOLADERE",
    ),
    "miramar": MunicodeConfig(
        municipality="Miramar",
        county="broward",
        client_id=3289,
        product_id=13202,
        job_id=479943,
        zoning_node_id="APXAFESC",
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

    # Summary
    summary: str = ""
    sources: list[str] = field(default_factory=list)
    confidence: str = ""  # "high", "medium", "low"
