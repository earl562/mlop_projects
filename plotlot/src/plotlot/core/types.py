"""Domain types for the plotlot zoning analysis platform.

All shared dataclasses and type definitions live here to prevent
circular imports and establish a single source of truth for the
domain model. Every other module imports from here.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid runtime cycle; Claim is defined in plotlot.domain.claims
    from plotlot.domain.claims import Claim


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
    """A raw section of ordinance text scraped from Municode.

    `path` is an optional explicit breadcrumb (the full ancestor heading chain,
    root-first). When absent the chunker synthesizes a path from
    `parent_heading` + `heading`. Slice 3.1 populates path/cross_refs at chunk
    time so every section carries a hierarchical location + its outbound
    references (the foundation for the `OrdinanceSection` index + AgenticRAG
    cross-ref traversal in Phase 8).
    """

    municipality: str
    county: str
    node_id: str
    heading: str
    parent_heading: str | None
    html_content: str
    depth: int
    path: list[str] | None = None


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
    """Metadata attached to each text chunk for filtering and retrieval.

    `path` is the section's hierarchical breadcrumb (root-first, e.g.
    ["Chapter 47", "Sec. 47-5.60"]); all chunks of one section share it.
    `cross_refs` are outbound section-number references found in the section
    text (e.g. ["47-24.3", "47-5.601"]). `section_type` classifies the section
    (regulation | definition | schedule | dimensional_table | use_regulation).
    These three are populated by the chunker (Slice 3.1) and feed the
    `OrdinanceSection` index used for cross-ref traversal + freshness checks.
    """

    municipality: str
    county: str
    chapter: str
    section: str
    section_title: str
    zone_codes: list[str]
    chunk_index: int
    municode_node_id: str
    path: list[str] = field(default_factory=list)
    cross_refs: list[str] = field(default_factory=list)
    section_type: str = "regulation"


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
    # Provenance of lot_size_sqft — gates whether a derived unit count may be
    # presented as firm. "assessor" = authoritative legal lot area (trustworthy);
    # "geometry" = derived from a parcel polygon (a GIS estimate that can diverge
    # from the recorded legal lot, so a unit count built on it is NOT firm); ""
    # = unknown. See pipeline/lookup.py and api/chat.py for how this gates trust.
    lot_size_source: str = ""

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
    # Provenance of the zoning params that fed this calculation.
    # "local_authority" — params came from a typed DistrictDimensionalStandard
    #   (a verified-fact row extracted from the ordinance's Schedule of District
    #   Regulations at ingestion time), so the resulting count is verified-fact
    #   grade, not LLM-extracted.
    # "unknown" — params came from LLM extraction over retrieved ordinance text
    #   (the legacy path); the count is assumption-grade until verified.
    # Mirrors the Claim origin taxonomy (claims.py: ClaimOrigin).
    origin: str = "unknown"
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


# ---------------------------------------------------------------------------
# Extraction verification — deterministic cross-check of LLM-extracted numbers
# ---------------------------------------------------------------------------


@dataclass
class FieldVerification:
    """Verification status for one LLM-extracted numeric value.

    Cross-checks the LLM value against an independent regex read of the source
    ordinance text (and, for density, the zone code's self-described value).
    """

    field: str  # e.g. "max_density_units_per_acre"
    label: str  # human label, e.g. "Max density (units/acre)"
    llm_value: float | None = None
    source_value: float | None = None  # value found deterministically in the text
    status: str = "unverified"  # "verified" | "conflict" | "unverified"
    citation: str = ""  # the matched source sentence (evidence)
    section: str = ""  # ordinance section the citation came from
    note: str = ""


@dataclass
class ExtractionVerification:
    """Aggregate verification of the value-drivers that set max buildable units."""

    fields: list[FieldVerification] = field(default_factory=list)
    overall: str = "unverified"  # "verified" | "partial" | "conflict" | "unverified"
    # True when a max-units driver (density / min lot area) is unverified or in
    # conflict — the offer must be shown as provisional, not firm.
    offer_is_provisional: bool = False
    warnings: list[str] = field(default_factory=list)


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
    state: str = ""  # two-letter state code (for regional cost model + comps)
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
    sensitivity: "SensitivityTable | None" = None
    entitlement: "EntitlementAssessment | None" = None
    density_uplift: "DensityUplift | None" = None

    # Summary
    summary: str = ""
    sources: list[str] = field(default_factory=list)
    confidence: str = ""  # "high", "medium", "low"

    # Deterministic plausibility warnings (e.g. implausible density, ADV from a
    # regional estimate). Surfaced so a human verifies before trusting numbers.
    warnings: list[str] = field(default_factory=list)

    # Per-value verification of LLM-extracted zoning numbers vs. the source text.
    extraction_verification: "ExtractionVerification | None" = None

    # Inline citations — maps extracted values back to source ordinance chunks
    source_refs: list[SourceRef] = field(default_factory=list)

    # Site risk — FEMA flood zone + NWI wetland data
    site_risk: "SiteRisk | None" = None

    # San Diego Coastal Height Limit Overlay (Prop D) — height → stories → units
    coastal_overlay: "CoastalHeightOverlay | None" = None

    # Development-activity signals (city permit system) — permit counts, active
    # permits, holders. Flags a parcel already in active development so it is not
    # pitched as raw land. Populated by pipeline/permits.fetch_development_signals.
    development_signals: dict | None = None

    # Entitlement timeline risk — real-time enhancement (CEQAnet, permits, etc.)
    entitlement_timeline_risk: "EntitlementTimelineRisk | None" = None

    # Neighbor/political opposition risk — qualitative heuristic assessment
    opposition_risk: "OppositionRiskAssessment | None" = None

    # Typed, provenanced claims emitted by _agentic_analysis (WIRE-2.1b).
    # Each Claim carries its kind (epistemic status) + origin (source boundary).
    # zoning.* claims are local_authority/verified_fact (grounded in ordinance
    # text or the GIS zone code); ungrounded LLM district assertions live under
    # the `assumed_zoning` namespace (origin=unknown, kind=assumption) because
    # the Claim invariant forbids zoning.* with non-local-authority origin.
    # standards.* claims carry origin per grounding. cost.*/financing.* are
    # never verified_fact (constructor-enforced). No ClaimLog storage yet
    # (Phase 6) — these are in-memory for downstream consumers.
    claims: list["Claim"] = field(default_factory=list)


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
    """CGS (California Geological Survey) seismic-hazard zones for a parcel.

    From the California statewide parcel layer's Earthquake Fault / Landslide /
    Liquefaction zone fields. Each value is the authoritative coded-value legend,
    NOT an interpretation. ``evaluated`` is False when CGS has not mapped the
    parcel for landslide/liquefaction (codes 3/4) — that is an honest "unknown,"
    never to be reported as "low risk."
    """

    fault_zone: str = ""  # Alquist-Priolo Earthquake Fault Zone status
    landslide_zone: str = ""  # CGS Seismic Hazard — landslide
    liquefaction_zone: str = ""  # CGS Seismic Hazard — liquefaction
    in_any_hazard_zone: bool = False  # within a mapped fault/landslide/liquefaction zone
    evaluated: bool = True  # False when CGS has not evaluated landslide/liquefaction
    flags: list[str] = field(default_factory=list)  # human-readable findings


@dataclass
class PermitRecord:
    """A single building/development permit from the city's permitting system.

    Retrieved from the City of San Diego's DSDPermits Accela layer.
    """

    permit_holder: str = ""
    permit_type: str = ""
    permit_status: str = ""
    issue_date: str = ""
    project_title: str = ""
    approval_url: str = ""


@dataclass
class SiteRisk:
    """Physical site risk flags drawn from FEMA NFHL, USFWS NWI, and CGS hazards."""

    flood_zone: FloodZoneInfo | None = None
    wetlands: list[WetlandInfo] = field(default_factory=list)
    has_wetlands: bool = False
    geologic: "GeologicHazard | None" = None
    # Airport Influence Areas the parcel falls in (City of San Diego DSD overlay),
    # e.g. "San Diego International Airport — Review Area 2". Empty when none.
    airport_influence: list[str] = field(default_factory=list)
    overall_risk: str = "unknown"  # "high", "moderate", "low", "unknown"
    risk_flags: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)


@dataclass
class CoastalHeightOverlay:
    """San Diego Coastal Height Limit Overlay Zone (Proposition D, 1972).

    A voter-enacted overlay capping structure height at 30 ft generally west of
    Interstate 5 in the City of San Diego. Membership is a *deterministic
    geographic* fact — a parcel is either inside the voter-mapped overlay polygon
    or it isn't — resolved by point-in-polygon against the City's authoritative
    DSD Zoning_Overlay layer. No LLM is involved, so there is no hallucination
    surface.

    ``status`` separates a *confirmed* determination from an *unverified* one so
    the firm unit count is only reduced when membership is known. An unverified
    result (City service unreachable) surfaces a warning instead of silently
    cutting units, per the fail-loud doctrine.
    """

    applies: bool = False  # confirmed inside the overlay → height_limit_ft applies
    height_limit_ft: float | None = None  # 30.0 when applies
    # "in" | "out" | "unverified" | "not_applicable"
    status: str = "not_applicable"
    zone_name: str = ""  # ZONENAME from the overlay layer
    citation: str = ""  # statutory / municipal-code reference
    source: str = ""  # data-source label
    note: str = ""


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
    Max Land Price = GDV - Hard Costs - Soft Costs - Builder Margin
    """

    gross_development_value: float = 0.0
    hard_costs: float = 0.0
    soft_costs: float = 0.0
    builder_margin: float = 0.0
    impact_fees: float = 0.0  # total government impact/development fees
    impact_fees_per_unit: float = 0.0
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
# Pro forma sensitivity analysis
# ---------------------------------------------------------------------------


@dataclass
class SensitivityTable:
    """Two-way sensitivity of the residual max land offer.

    The residual land value is a single point estimate built on uncertain
    assumptions. This sweeps the two most impactful drivers — ADV per unit
    (revenue) across columns and construction cost per sqft (cost) down rows —
    and records the resulting max land offer in ``grid[row][col]``. Cells where
    the offer is negative mark deals that no longer pencil.
    """

    row_label: str = "Construction $/sf"
    col_label: str = "ADV per Unit"
    row_values: list[float] = field(default_factory=list)  # construction $/sf
    col_values: list[float] = field(default_factory=list)  # ADV per unit
    grid: list[list[float]] = field(default_factory=list)  # max_land_price[row][col]
    base_row_index: int = 0
    base_col_index: int = 0
    base_value: float = 0.0  # base-case max land offer (the headline number)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Entitlement path + impact fees ("what it takes to build")
# ---------------------------------------------------------------------------


@dataclass
class EntitlementStep:
    """One step on the path from raw land to a building permit."""

    name: str
    status: str  # "required" | "likely" | "conditional" | "not_needed"
    timeline_months: float
    note: str = ""


@dataclass
class EntitlementAssessment:
    """The approval path, timeline, and government fees to build the project.

    Deterministic: the path is classified from the zoning use lists, and fees
    come from the regional cost model — no LLM involvement.
    """

    path: str = "unknown"  # "by_right" | "conditional_use" | "rezoning" | "unknown"
    complexity: str = "unknown"  # "low" | "medium" | "high" | "unknown"
    steps: list[EntitlementStep] = field(default_factory=list)
    est_timeline_months: float = 0.0
    impact_fee_per_unit: float = 0.0
    impact_fees_total: float = 0.0
    fee_market: str = ""  # regional cost-model label the fee came from
    utilities_note: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# California state-program density uplift (ADU / SB9 / Density Bonus)
# ---------------------------------------------------------------------------


@dataclass
class UpliftProgram:
    """One California statute that can add units above base zoning."""

    name: str
    statute: str
    applies: bool = True
    eligibility: str = "eligible"  # "eligible" | "restricted" | "ineligible"
    source: str = "state"  # "state" (deterministic) | "local" (verified LLM override)
    additional_units: int = 0  # units added over base via this program
    potential_units: int = 0  # base + additional for this pathway
    basis: str = ""  # plain-language explanation of the math
    requirements: str = ""  # conditions to actually achieve it


@dataclass
class LocalOverride:
    """A local-ordinance provision the LLM proposed to exceed the state baseline.

    The number is *proposed* by the LLM but only trusted after a deterministic
    check that the cited quote is verbatim in the retrieved ordinance text and
    contains the value. Unverified overrides are surfaced but never applied.
    """

    field: str  # e.g. "local_adu_additional" | "local_density_bonus_pct"
    label: str
    value: float
    quote: str = ""  # the verbatim ordinance sentence the LLM cited
    section: str = ""
    status: str = "unverified"  # "verified" | "unverified"
    note: str = ""


@dataclass
class DensityUplift:
    """Additive 'potential' overlay on top of the verified base unit count.

    State programs are deterministic (statute constants). Optional *local*
    overrides come from the LLM but are applied only when a deterministic check
    corroborates them against the ordinance text. The base zoning count stays the
    firm number; this is shown separately as upside, never folded into the offer.
    """

    base_units: int = 0
    state: str = ""
    programs: list[UpliftProgram] = field(default_factory=list)
    max_potential_units: int = 0  # best single applicable pathway
    local_overrides: list[LocalOverride] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class UpzoningScenario:
    """One development scenario for a parcel — a yield and the gross value it earns.

    Used to compare what a parcel is worth under different entitlement states: its
    as-is by-right yield vs. an upzoned / subdivided target. ``yield_count`` is
    lots (fee-simple subdivision) or dwelling units, per ``yield_basis``. Every
    figure is deterministic; ``value_per_yield`` is an INPUT (comps or override),
    never fabricated — there is no free sold-lot price source.
    """

    name: str  # e.g. "By-right subdivision", "Upzoned (special use permit)"
    yield_count: int  # number of lots/units this scenario produces
    yield_basis: str  # "buildable lots" | "dwelling units"
    value_per_yield: float  # finished value per lot/unit
    gross_value: float  # yield_count × value_per_yield
    instant_equity: float  # gross_value − all-in basis
    is_baseline: bool = False
    formula: str = ""  # how the yield was derived
    notes: list[str] = field(default_factory=list)


@dataclass
class UpzoningAnalysis:
    """Entitlement value-creation — the equity created by upzoning before building.

    Models the land developer's core play: buy at a basis, change the legal yield
    (subdivide / rezone / SUP), and capture the value uplift *before* construction.
    All figures are deterministic. ``value_source`` flags whether the per-lot value
    came from comps, a caller override, or is missing — when missing, the equity is
    left uncomputed by design rather than guessed (anti-hallucination doctrine).
    """

    purchase_price: float
    entitlement_soft_costs: float
    all_in_basis: float  # purchase_price + entitlement_soft_costs
    value_source: str  # "comps" | "override" | "missing"
    baseline: UpzoningScenario | None = None
    upzoned: UpzoningScenario | None = None
    value_uplift: float = 0.0  # upzoned.gross_value − baseline.gross_value
    equity_created: float = 0.0  # the upzoned scenario's instant equity (headline)
    cost_per_yield: float = 0.0  # all_in_basis ÷ upzoned.yield_count
    exit_options: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Entitlement timeline risk — real-time enhancement of the base assessment
# ---------------------------------------------------------------------------


@dataclass
class CEQADocument:
    """A CEQA document for a project, retrieved live from CEQAnet.

    Pulled from the State Clearinghouse CSV export (``ceqanet.lci.ca.gov``) —
    these are REAL filed documents, not LLM guesses. ``doc_type`` indicates the
    likely review timeline: NOE/CE (exemption) = none, ND/MND = 3–8mo, EIR
    (NOP→EIR) = 12–24mo+. Location fields are populated for local projects and
    blank for statewide/programmatic actions. ``match_tier`` records how
    confidently the document was tied to the subject parcel (see
    ``pipeline/ceqanet.py``): "strong" = APN exact or within the strong-match
    radius (may drive the timeline); "candidate" = same city + a weaker signal
    (display-only, never drives the timeline or confidence).
    """

    doc_type: str  # "EIR" | "MND" | "ND" | "NOP" | "NOE" | "NOD" | "Other"
    status: str = ""  # e.g. "in_progress", "completed", "exempt"
    filed_date: str = ""
    description: str = ""
    lead_agency: str = ""
    on_parcel: bool = False  # True iff match_tier == "strong"
    source_url: str = ""  # CEQAnet Document Portal URL for this SCH
    # Structured location/identity fields from the CEQAnet CSV export
    sch_number: str = ""
    title: str = ""
    coordinates: str = ""  # raw DMS string as published
    lat: float | None = None  # parsed decimal degrees
    lng: float | None = None
    parcel_number: str = ""  # as published (may be a real APN or free text)
    cross_streets: str = ""
    zip_code: str = ""
    cities: str = ""
    counties: str = ""
    contact_name: str = ""
    # Match metadata (set by the matcher in pipeline/ceqanet.py)
    match_tier: str = ""  # "strong" | "candidate" | ""
    match_basis: str = ""  # human-readable reason, e.g. "APN 760-057-00-02 exact"
    match_confidence: float = 0.0  # 0..1
    distance_m: float | None = None  # metres from parcel when coordinates known


@dataclass
class EntitlementTimelineRisk:
    """Expanded timeline risk assessment factoring in real-time checks.

    Augments the base ``EntitlementAssessment.est_timeline_months`` with a
    risk range, confidence level, and key drivers identified from live data.
    """

    est_months_min: float = 0.0  # optimistic best-case
    est_months_max: float = 0.0  # pessimistic worst-case (incl. hearings, appeals)
    risk_level: str = "unknown"  # "low" | "moderate" | "high" | "unknown"
    confidence: str = "low"  # "high" | "medium" | "low"
    key_drivers: list[str] = field(default_factory=list)
    ceqa_documents: list[CEQADocument] = field(default_factory=list)  # Tier 1: strong matches
    ceqa_candidates: list[CEQADocument] = field(  # Tier 2: display-only, never drives
        default_factory=list
    )
    active_permits_exist: bool = False
    data_sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Neighbor / political opposition risk assessment (qualitative)
# ---------------------------------------------------------------------------


@dataclass
class AdjacentUse:
    """Land use and zoning of an adjacent parcel."""

    zoning: str = ""
    land_use: str = ""
    distance_ft: float = 0.0


@dataclass
class OppositionRiskAssessment:
    """Qualitative assessment of neighbor/political opposition risk.

    Based on parcel context: density delta, adjacent uses, zoning history,
    and (when available) web search for recent planning controversies in the
    municipality. This is a HEURISTIC assessment, not a data-driven model —
    always labeled as qualitative.
    """

    risk_level: str = "unknown"  # "low" | "moderate" | "high" | "unknown"
    flags: list[str] = field(default_factory=list)
    adjacent_uses: list[AdjacentUse] = field(default_factory=list)
    density_delta_description: str = ""
    assessment: str = ""  # plain-language qualitative write-up
    data_sources: list[str] = field(default_factory=list)
    confidence: str = "low"  # always "low" — this is inherently qualitative


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
