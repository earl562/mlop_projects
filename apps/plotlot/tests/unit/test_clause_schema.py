"""Tests for clause builder Pydantic models and enums."""

from plotlot.clauses.schema import (
    AssemblyConfig,
    ClauseCategory,
    ClauseFormatting,
    ContractClause,
    DealContext,
    DealType,
    DocumentType,
    RenderedClause,
)


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


class TestDealType:
    def test_all_deal_types(self):
        expected = {
            "wholesale",
            "subject_to",
            "wrap",
            "hybrid",
            "seller_finance",
            "option",
            "jv",
            "land_deal",
        }
        assert {dt.value for dt in DealType} == expected

    def test_string_enum(self):
        assert DealType.subject_to == "subject_to"
        assert str(DealType.wrap) == "DealType.wrap"


class TestDocumentType:
    def test_all_document_types(self):
        expected = {
            "loi",
            "psa",
            "deal_summary",
            "proforma_spreadsheet",
            "addendum",
            "acknowledgements",
            "promissory_note",
            "deed_of_trust",
        }
        assert {dt.value for dt in DocumentType} == expected


class TestClauseCategory:
    def test_all_categories(self):
        expected = {
            "party_identification",
            "property_definition",
            "financial_terms",
            "contingencies",
            "reps_warranties",
            "risk_liability",
            "legal_admin",
            "dispute_resolution",
            "closing",
            "signatures",
        }
        assert {c.value for c in ClauseCategory} == expected


# ---------------------------------------------------------------------------
# ContractClause
# ---------------------------------------------------------------------------


class TestContractClause:
    def test_minimal_clause(self):
        clause = ContractClause(
            id="test.minimal",
            category=ClauseCategory.financial_terms,
            title="Test Clause",
            document_types=[DocumentType.loi],
            content_template="Price: {{ context.purchase_price }}",
        )
        assert clause.id == "test.minimal"
        assert clause.is_required is True
        assert clause.order_weight == 100
        assert clause.condition_expr is None
        assert clause.group_id is None
        assert clause.version == "1.0"

    def test_effective_slug_from_slug(self):
        clause = ContractClause(
            id="loi.price",
            slug="loi-price",
            category=ClauseCategory.financial_terms,
            title="Price",
            document_types=[DocumentType.loi],
            content_template="",
        )
        assert clause.effective_slug() == "loi-price"

    def test_effective_slug_fallback(self):
        clause = ContractClause(
            id="loi.price.breakdown",
            category=ClauseCategory.financial_terms,
            title="Price",
            document_types=[DocumentType.loi],
            content_template="",
        )
        assert clause.effective_slug() == "loi-price-breakdown"

    def test_full_clause(self):
        clause = ContractClause(
            id="psa.financing_subject_to",
            slug="psa-financing-subject-to",
            category=ClauseCategory.financial_terms,
            title="Subject-To Financing",
            deal_types=[DealType.subject_to, DealType.wrap],
            document_types=[DocumentType.psa],
            order_weight=310,
            content_template="Buyer purchasing subject to existing mortgage of ${{ context.existing_mortgage_balance_1 }}",
            is_required=False,
            condition_expr="context.financing_type == 'subject_to'",
            group_id="financing_type",
            state_variants={"TX": "Contract for Deed variant text"},
            formatting=ClauseFormatting(heading_level=3, style="numbered_list"),
            source="SubTo PSA Section 3",
            version="2.0",
            notes="Mirror/Hybrid/Seller carryback are mutually exclusive",
        )
        assert clause.group_id == "financing_type"
        assert DealType.subject_to in clause.deal_types
        assert clause.formatting is not None
        assert clause.formatting.heading_level == 3

    def test_default_deal_types_includes_all(self):
        clause = ContractClause(
            id="shared.test",
            category=ClauseCategory.legal_admin,
            title="Test",
            document_types=[DocumentType.psa],
            content_template="",
        )
        assert len(clause.deal_types) == len(DealType)


# ---------------------------------------------------------------------------
# DealContext
# ---------------------------------------------------------------------------


class TestDealContext:
    def test_defaults(self):
        ctx = DealContext()
        assert ctx.state_code == "FL"
        assert ctx.deal_type == DealType.land_deal
        assert ctx.inspection_days == 30
        assert ctx.earnest_money_pct == 1.0
        assert len(ctx.contingencies) == 3
        assert ctx.financing_contingency is True

    def test_populated(self):
        ctx = DealContext(
            property_address="7940 Plantation Blvd, Miramar, FL 33023",
            buyer_name="Earl Perry",
            buyer_entity="EP Investments LLC",
            purchase_price=500_000,
            deal_type=DealType.subject_to,
            financing_type="subject_to",
            existing_mortgage_balance_1=350_000,
        )
        assert ctx.purchase_price == 500_000
        assert ctx.financing_type == "subject_to"

    def test_empty_strings_for_placeholders(self):
        ctx = DealContext()
        assert ctx.buyer_name == ""
        assert ctx.seller_name == ""
        assert ctx.escrow_agent_name == ""


# ---------------------------------------------------------------------------
# AssemblyConfig
# ---------------------------------------------------------------------------


class TestAssemblyConfig:
    def test_defaults(self):
        config = AssemblyConfig(document_type=DocumentType.loi)
        assert config.deal_type == DealType.land_deal
        assert config.state_code == "FL"
        assert config.output_format == "docx"
        assert config.include_plotlot_branding is True
        assert config.exclude_clause_ids == []

    def test_custom(self):
        config = AssemblyConfig(
            document_type=DocumentType.psa,
            deal_type=DealType.subject_to,
            state_code="TX",
            output_format="pdf",
            exclude_clause_ids=["psa.lead_paint"],
        )
        assert config.state_code == "TX"
        assert "psa.lead_paint" in config.exclude_clause_ids


# ---------------------------------------------------------------------------
# RenderedClause
# ---------------------------------------------------------------------------


class TestRenderedClause:
    def test_basic(self):
        rc = RenderedClause(
            id="loi.price",
            title="Purchase Price",
            category=ClauseCategory.financial_terms,
            rendered_content="Purchase Price: $500,000",
        )
        assert rc.rendered_content == "Purchase Price: $500,000"
        assert rc.order_weight == 100


# ---------------------------------------------------------------------------
# ClauseFormatting
# ---------------------------------------------------------------------------


class TestClauseFormatting:
    def test_defaults(self):
        fmt = ClauseFormatting()
        assert fmt.heading_level == 2
        assert fmt.style == "normal"
        assert fmt.page_break_before is False
        assert fmt.columns is None

    def test_table_style(self):
        fmt = ClauseFormatting(
            style="table",
            columns=["Term", "Value"],
        )
        assert fmt.columns == ["Term", "Value"]
