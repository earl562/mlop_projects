"""Pydantic models for the Clause Builder system.

Defines the contract clause data model, deal context (template rendering
data bag), assembly configuration, and all supporting enums.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DealType(str, Enum):
    """Types of real estate deals the clause builder supports."""

    wholesale = "wholesale"
    subject_to = "subject_to"
    wrap = "wrap"
    hybrid = "hybrid"
    seller_finance = "seller_finance"
    option = "option"
    jv = "jv"
    land_deal = "land_deal"


class DocumentType(str, Enum):
    """Types of documents the clause builder can generate."""

    loi = "loi"
    psa = "psa"
    deal_summary = "deal_summary"
    proforma_spreadsheet = "proforma_spreadsheet"
    addendum = "addendum"
    acknowledgements = "acknowledgements"
    promissory_note = "promissory_note"
    deed_of_trust = "deed_of_trust"


class ClauseCategory(str, Enum):
    """Semantic categories for organizing clauses."""

    party_identification = "party_identification"
    property_definition = "property_definition"
    financial_terms = "financial_terms"
    contingencies = "contingencies"
    reps_warranties = "reps_warranties"
    risk_liability = "risk_liability"
    legal_admin = "legal_admin"
    dispute_resolution = "dispute_resolution"
    closing = "closing"
    signatures = "signatures"


# ---------------------------------------------------------------------------
# Clause Model
# ---------------------------------------------------------------------------


class ClauseFormatting(BaseModel):
    """Rendering metadata for docx/PDF output."""

    heading_level: int = 2
    style: str = "normal"  # "normal", "table", "checklist", "numbered_list"
    page_break_before: bool = False
    columns: list[str] | None = None  # for table-style clauses


class ContractClause(BaseModel):
    """An atomic, reusable contract clause.

    Clauses are loaded from YAML definitions, filtered by document type
    and deal type, conditionally included based on DealContext, and
    rendered via Jinja2 templates.
    """

    id: str = Field(..., description="Unique clause identifier, e.g. 'loi.purchase_price'")
    slug: str = Field("", description="URL-safe identifier (auto-generated from id if empty)")
    category: ClauseCategory
    title: str = Field(..., description="Human-readable heading")
    deal_types: list[DealType] = Field(
        default_factory=lambda: list(DealType),
        description="Which deal types use this clause",
    )
    document_types: list[DocumentType] = Field(
        ..., description="Which document types use this clause"
    )
    order_weight: int = Field(default=100, description="Sort position within document")
    content_template: str = Field(
        ..., description="Jinja2 template string with {{ context.field }} variables"
    )
    is_required: bool = True
    condition_expr: str | None = Field(
        default=None,
        description="Dot-path condition, e.g. 'context.financing_type == subject_to'",
    )
    group_id: str | None = Field(
        default=None,
        description="Mutually exclusive group — only one clause per group_id is included",
    )
    state_variants: dict[str, str] | None = Field(
        default=None,
        description="State code -> override template, e.g. {'TX': 'Contract for Deed...'}",
    )
    formatting: ClauseFormatting | None = None
    source: str = Field(default="", description="Origin reference, e.g. 'SubTo PSA Section 3'")
    version: str = "1.0"
    notes: str = ""

    def effective_slug(self) -> str:
        """Return slug, falling back to id with dots replaced by hyphens."""
        return self.slug or self.id.replace(".", "-")


# ---------------------------------------------------------------------------
# Deal Context — data bag for Jinja2 rendering
# ---------------------------------------------------------------------------


class DealContext(BaseModel):
    """All data needed to render clause templates.

    Combines pipeline analysis data with user-provided deal terms.
    Fields left empty render as [TBD] placeholders in the output.
    """

    # --- Property (from pipeline or user override) ---
    property_address: str = ""
    formatted_address: str = ""
    apn: str = ""  # APN / folio number
    legal_description: str = ""
    municipality: str = ""
    county: str = ""
    state_code: str = "FL"
    lot_size_sqft: float = 0.0
    year_built: int = 0
    owner: str = ""

    # --- Zoning (from pipeline) ---
    zoning_district: str = ""
    zoning_description: str = ""
    max_units: int = 0
    governing_constraint: str = ""
    max_height: str = ""
    max_density: str = ""
    allowed_uses: list[str] = Field(default_factory=list)

    # --- Comps (from pipeline) ---
    median_price_per_acre: float = 0.0
    estimated_land_value: float = 0.0
    comp_count: int = 0
    comp_confidence: float = 0.0

    # --- Pro forma (from pipeline) ---
    gross_development_value: float = 0.0
    hard_costs: float = 0.0
    soft_costs: float = 0.0
    builder_margin: float = 0.0
    max_land_price: float = 0.0
    cost_per_door: float = 0.0
    adv_per_unit: float = 0.0

    # --- Parties (user-provided) ---
    buyer_name: str = ""
    buyer_entity: str = ""
    buyer_email: str = ""
    buyer_phone: str = ""
    buyer_address: str = ""
    seller_name: str = ""
    seller_entity: str = ""
    seller_email: str = ""
    seller_phone: str = ""
    seller_address: str = ""

    # --- Escrow / Closing ---
    escrow_agent_name: str = ""
    escrow_agent_address: str = ""
    escrow_agent_phone: str = ""
    escrow_agent_email: str = ""

    # --- Financial terms ---
    purchase_price: float = 0.0
    earnest_money: float = 0.0
    earnest_money_pct: float = 1.0
    option_fee: float = 0.0
    down_payment: float = 0.0
    cash_at_closing: float = 0.0
    net_to_seller: float = 0.0

    # --- Deal type & financing ---
    deal_type: DealType = DealType.land_deal
    financing_type: str = ""  # "subject_to", "wrap", "hybrid", "seller_carryback", "cash"
    existing_mortgage_balance_1: float = 0.0
    existing_mortgage_balance_2: float = 0.0
    existing_mortgage_payment: float = 0.0
    existing_mortgage_rate: float = 0.0
    seller_carryback_amount: float = 0.0
    seller_carryback_rate: float = 0.0
    seller_carryback_term_months: int = 0
    seller_carryback_payment: float = 0.0
    new_loan_amount: float = 0.0
    wrap_rate: float = 0.0
    wrap_payment: float = 0.0
    additional_principal: float = 0.0

    # --- Periods ---
    inspection_days: int = 30
    due_diligence_days: int = 30
    closing_days: int = 60
    feasibility_days: int = 45
    option_expiration_days: int = 90
    financing_contingency_days: int = 0

    # --- Contingencies ---
    contingencies: list[str] = Field(
        default_factory=lambda: [
            "Satisfactory zoning verification",
            "Environmental assessment (Phase I)",
            "Clear title and survey",
        ]
    )
    financing_contingency: bool = True
    appraisal_contingency: bool = True
    inspection_contingency: bool = True

    # --- Entitlement / upzoning contingency (the land-deal value-creation play:
    # control the parcel cheaply, then create value by rezoning/subdividing BEFORE
    # closing). Off by default — only included when the buyer is pursuing an upzone. ---
    entitlement_contingency: bool = False  # gate the rezoning/upzoning contingency clause
    upzoning_vehicle: str = ""  # e.g. "special use permit", "rezoning", "PUD", "variance"
    entitlement_close_days: int = 0  # total days to close while pursuing approval (e.g. 365)
    entitlement_extension_days: int = 0  # extension option if approval is delayed (e.g. 180)
    target_units: int = 0  # the upzoned unit/lot yield the buyer is pursuing (for reference)

    # --- JV-specific ---
    jv_profit_split_pct: float = 50.0
    jv_expense_split_pct: float = 50.0
    jv_managing_member: str = ""

    # --- Broker ---
    seller_broker_name: str = ""
    seller_broker_phone: str = ""
    seller_broker_email: str = ""
    buyer_broker_name: str = ""
    buyer_broker_phone: str = ""
    buyer_broker_email: str = ""
    commission_pct: float = 0.0

    # --- Dates ---
    effective_date: str = ""
    closing_date: str = ""
    expiration_date: str = ""
    maturity_date: str = ""

    # --- AI summary ---
    summary: str = ""
    confidence: str = ""
    sources: list[str] = Field(default_factory=list)

    # --- Metadata ---
    generated_at: str = ""
    document_type: DocumentType = DocumentType.loi


# ---------------------------------------------------------------------------
# Assembly Config
# ---------------------------------------------------------------------------


class AssemblyConfig(BaseModel):
    """Instructions for the assembly engine."""

    document_type: DocumentType
    deal_type: DealType = DealType.land_deal
    state_code: str = "FL"
    output_format: str = Field(
        default="docx",
        description="Output format: 'docx', 'pdf', 'xlsx', 'google_sheets'",
    )
    include_plotlot_branding: bool = True
    exclude_clause_ids: list[str] = Field(default_factory=list)
    override_order: dict[str, int] | None = None


# ---------------------------------------------------------------------------
# Rendered Clause (intermediate output)
# ---------------------------------------------------------------------------


class RenderedClause(BaseModel):
    """A clause after Jinja2 rendering — ready for document assembly."""

    id: str
    title: str
    category: ClauseCategory
    rendered_content: str
    formatting: ClauseFormatting | None = None
    order_weight: int = 100
    is_required: bool = True


# ---------------------------------------------------------------------------
# Generated Document
# ---------------------------------------------------------------------------


class GeneratedDocument(BaseModel):
    """A generated document ready for download.

    Canonical location for the clause builder system. Previously lived in
    pipeline/contracts.py as a dataclass — migrated to Pydantic for
    consistency with the rest of the clause builder.
    """

    filename: str
    content_type: str
    data: bytes
