"""Tests for PSA (Purchase and Sale Agreement) generation via the clause builder."""

from pathlib import Path

from plotlot.clauses.engine import assemble_clauses, assemble_document
from plotlot.clauses.loader import ClauseRegistry
from plotlot.clauses.schema import (
    AssemblyConfig,
    DealContext,
    DealType,
    DocumentType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DEFINITIONS_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "plotlot" / "clauses" / "definitions"
)


def _registry() -> ClauseRegistry:
    return ClauseRegistry.from_directory(_DEFINITIONS_DIR)


def _subject_to_context() -> DealContext:
    """Subject-to deal context."""
    return DealContext(
        property_address="456 Oak Ave, Fort Lauderdale, FL 33301",
        apn="5042-22-01-0030",
        legal_description="Lot 12, Block 3, Oak Hills Subdivision",
        state_code="FL",
        county="Broward",
        deal_type=DealType.subject_to,
        financing_type="subject_to",
        purchase_price=350000.0,
        earnest_money=5000.0,
        existing_mortgage_balance_1=280000.0,
        existing_mortgage_payment=1850.0,
        existing_mortgage_rate=4.25,
        cash_at_closing=70000.0,
        inspection_days=15,
        closing_days=45,
        buyer_name="EP Ventures LLC",
        buyer_entity="EP Ventures LLC",
        buyer_email="deals@epventures.com",
        buyer_address="100 Business Ave, Suite 200, Miami, FL 33131",
        seller_name="Jane Doe",
        seller_address="456 Oak Ave, Fort Lauderdale, FL 33301",
        seller_email="janedoe@email.com",
        escrow_agent_name="First Title Co.",
        escrow_agent_address="500 Title Blvd, Fort Lauderdale, FL 33301",
        escrow_agent_phone="(954) 555-1234",
        escrow_agent_email="closing@firsttitle.com",
    )


def _seller_finance_context() -> DealContext:
    """Seller carryback deal context."""
    return DealContext(
        property_address="789 Pine St, Miami, FL 33101",
        apn="01-4321-000-0001",
        state_code="FL",
        deal_type=DealType.seller_finance,
        financing_type="seller_carryback",
        purchase_price=500000.0,
        earnest_money=10000.0,
        down_payment=50000.0,
        seller_carryback_amount=450000.0,
        seller_carryback_rate=6.0,
        seller_carryback_term_months=360,
        seller_carryback_payment=2698.0,
        inspection_days=20,
        closing_days=60,
        buyer_name="EP Holdings LLC",
        seller_name="John Smith",
    )


def _cash_context() -> DealContext:
    """Cash / wholesale deal context."""
    return DealContext(
        property_address="321 Elm Dr, West Palm Beach, FL 33401",
        apn="12-43-44-05-01-000-0010",
        state_code="FL",
        deal_type=DealType.wholesale,
        financing_type="cash",
        purchase_price=225000.0,
        earnest_money=5000.0,
        inspection_days=10,
        closing_days=30,
        buyer_name="Quick Close LLC",
        seller_name="Estate of Robert Jones",
    )


def _pre1978_context() -> DealContext:
    """Pre-1978 property (triggers lead paint clause)."""
    return DealContext(
        property_address="100 Vintage Ln, Miami, FL 33101",
        state_code="FL",
        deal_type=DealType.subject_to,
        financing_type="subject_to",
        year_built=1965,
        purchase_price=300000.0,
        buyer_name="EP Ventures LLC",
        seller_name="Historic Homes Inc.",
    )


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------


class TestPSARegistry:
    def test_psa_clauses_exist(self):
        registry = _registry()
        clauses = registry.get(DocumentType.psa)
        # PSA-specific (13) + shared with psa in doc_types (~8)
        assert len(clauses) >= 13, f"Expected >=13 PSA clauses, got {len(clauses)}"

    def test_psa_has_parties(self):
        registry = _registry()
        clause = registry.get_by_id("psa.parties")
        assert clause is not None
        assert DocumentType.psa in clause.document_types

    def test_psa_has_financing_groups(self):
        """PSA should have mutually exclusive financing clauses."""
        registry = _registry()
        clauses = registry.get(DocumentType.psa)
        groups = registry.get_groups(clauses)
        assert "psa_financing" in groups
        assert len(groups["psa_financing"]) == 3  # cash, subject_to, seller_finance

    def test_shared_clauses_included(self):
        """Shared clauses marked for PSA should be in the result set."""
        registry = _registry()
        clauses = registry.get(DocumentType.psa)
        ids = {c.id for c in clauses}
        expected_shared = {
            "shared.reps_warranties_buyer",
            "shared.reps_warranties_seller",
            "shared.governing_law",
            "shared.severability",
            "shared.counterparts",
            "shared.notices",
            "shared.entire_agreement",
            "shared.time_of_essence",
            "shared.signature_block",
        }
        for shared_id in expected_shared:
            assert shared_id in ids, f"Missing shared clause: {shared_id}"


# ---------------------------------------------------------------------------
# Mutually exclusive financing groups
# ---------------------------------------------------------------------------


class TestPSAFinancingGroups:
    def test_subject_to_selects_subject_to_pricing(self):
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.subject_to)
        context = _subject_to_context()
        rendered = assemble_clauses(config, context, registry)

        ids = {r.id for r in rendered}
        assert "psa.purchase_price_subject_to" in ids
        assert "psa.purchase_price_cash" not in ids
        assert "psa.purchase_price_seller_finance" not in ids

    def test_seller_finance_selects_seller_finance_pricing(self):
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.seller_finance)
        context = _seller_finance_context()
        rendered = assemble_clauses(config, context, registry)

        ids = {r.id for r in rendered}
        assert "psa.purchase_price_seller_finance" in ids
        assert "psa.purchase_price_subject_to" not in ids
        assert "psa.purchase_price_cash" not in ids

    def test_cash_selects_cash_pricing(self):
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.wholesale)
        context = _cash_context()
        rendered = assemble_clauses(config, context, registry)

        ids = {r.id for r in rendered}
        assert "psa.purchase_price_cash" in ids
        assert "psa.purchase_price_subject_to" not in ids
        assert "psa.purchase_price_seller_finance" not in ids


# ---------------------------------------------------------------------------
# Conditional clauses
# ---------------------------------------------------------------------------


class TestPSAConditionals:
    def test_lead_paint_included_for_pre1978(self):
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.subject_to)
        context = _pre1978_context()
        rendered = assemble_clauses(config, context, registry)

        ids = {r.id for r in rendered}
        assert "psa.lead_paint" in ids

    def test_lead_paint_excluded_for_post1978(self):
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.subject_to)
        context = _subject_to_context()  # year_built=0, condition year_built < 1978 fails
        rendered = assemble_clauses(config, context, registry)

        # year_built=0 means 0 < 1978 is True, so lead_paint IS included for default context.
        # Test with a post-1978 year to verify exclusion.
        context.year_built = 2005
        rendered = assemble_clauses(config, context, registry)
        ids = {r.id for r in rendered}
        assert "psa.lead_paint" not in ids


# ---------------------------------------------------------------------------
# Rendering content
# ---------------------------------------------------------------------------


class TestPSARendering:
    def test_parties_renders_buyer_seller(self):
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.subject_to)
        context = _subject_to_context()
        rendered = assemble_clauses(config, context, registry)

        parties = next(r for r in rendered if r.id == "psa.parties")
        assert "EP Ventures LLC" in parties.rendered_content
        assert "Jane Doe" in parties.rendered_content

    def test_subject_to_renders_mortgage_details(self):
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.subject_to)
        context = _subject_to_context()
        rendered = assemble_clauses(config, context, registry)

        price_clause = next(r for r in rendered if r.id == "psa.purchase_price_subject_to")
        assert "280,000" in price_clause.rendered_content  # existing mortgage balance
        assert "350,000" in price_clause.rendered_content  # purchase price

    def test_escrow_renders_closing_details(self):
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.subject_to)
        context = _subject_to_context()
        rendered = assemble_clauses(config, context, registry)

        escrow = next(r for r in rendered if r.id == "psa.escrow_closing")
        assert "First Title Co." in escrow.rendered_content
        assert "45" in escrow.rendered_content  # closing_days

    def test_notices_renders_addresses(self):
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.subject_to)
        context = _subject_to_context()
        rendered = assemble_clauses(config, context, registry)

        notices = next(r for r in rendered if r.id == "shared.notices")
        assert "EP Ventures LLC" in notices.rendered_content
        assert "Jane Doe" in notices.rendered_content

    def test_clause_ordering(self):
        """Clauses should be sorted: parties → property → financials → ... → signatures."""
        registry = _registry()
        config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.subject_to)
        context = _subject_to_context()
        rendered = assemble_clauses(config, context, registry)

        weights = [r.order_weight for r in rendered]
        assert weights == sorted(weights), f"Clauses not sorted: {weights}"

        # Parties should be first, signatures last
        assert rendered[0].id == "psa.parties"
        assert rendered[-1].id in ("shared.signature_block", "shared.plotlot_footer")


# ---------------------------------------------------------------------------
# Docx output
# ---------------------------------------------------------------------------


class TestPSADocx:
    def test_subject_to_generates_valid_docx(self):
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.psa,
            deal_type=DealType.subject_to,
            output_format="docx",
        )
        context = _subject_to_context()
        doc = assemble_document(config, context, registry)

        assert doc.data[:4] == b"PK\x03\x04"
        assert doc.filename.startswith("PSA_")
        assert doc.filename.endswith(".docx")
        assert len(doc.data) > 2000  # PSA is a substantial document

    def test_seller_finance_generates_valid_docx(self):
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.psa,
            deal_type=DealType.seller_finance,
            output_format="docx",
        )
        context = _seller_finance_context()
        doc = assemble_document(config, context, registry)

        assert doc.data[:4] == b"PK\x03\x04"
        assert len(doc.data) > 2000

    def test_cash_wholesale_generates_valid_docx(self):
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.psa,
            deal_type=DealType.wholesale,
            output_format="docx",
        )
        context = _cash_context()
        doc = assemble_document(config, context, registry)

        assert doc.data[:4] == b"PK\x03\x04"
        assert len(doc.data) > 2000

    def test_psa_has_more_clauses_than_deal_summary(self):
        """PSA should be a more comprehensive document than a deal summary."""
        registry = _registry()
        psa_config = AssemblyConfig(document_type=DocumentType.psa, deal_type=DealType.subject_to)
        ds_config = AssemblyConfig(
            document_type=DocumentType.deal_summary, deal_type=DealType.land_deal
        )
        psa_ctx = _subject_to_context()
        ds_ctx = DealContext(
            property_address="Test",
            max_units=4,
            median_price_per_acre=100000,
            max_land_price=500000,
            summary="test",
        )

        psa_rendered = assemble_clauses(psa_config, psa_ctx, registry)
        ds_rendered = assemble_clauses(ds_config, ds_ctx, registry)

        assert len(psa_rendered) > len(ds_rendered)
