"""Tests for Deal Summary document generation via the clause builder."""

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


def _full_context() -> DealContext:
    """A DealContext with all fields populated for a land deal analysis."""
    return DealContext(
        property_address="7940 Plantation Blvd, Miramar, FL 33023",
        formatted_address="7940 Plantation Blvd, Miramar, FL 33023",
        apn="5040-19-02-0010",
        municipality="Miramar",
        county="Broward",
        state_code="FL",
        lot_size_sqft=15000.0,
        year_built=1975,
        owner="Smith Family Trust",
        zoning_district="RS-4",
        zoning_description="Residential Single Family, 4 units/acre",
        max_units=4,
        governing_constraint="density",
        max_height="35 feet",
        max_density="4 units/acre",
        allowed_uses=["single-family", "duplex", "townhome"],
        median_price_per_acre=450000.0,
        estimated_land_value=155000.0,
        comp_count=8,
        comp_confidence=0.82,
        gross_development_value=1600000.0,
        hard_costs=800000.0,
        soft_costs=120000.0,
        builder_margin=0.12,
        max_land_price=488000.0,
        cost_per_door=230000.0,
        adv_per_unit=400000.0,
        deal_type=DealType.land_deal,
        summary="Strong development potential with 4 units allowed. Comparable land trades at $450K/acre.",
        confidence="high",
        sources=["Broward County ArcGIS", "Miramar Zoning Ordinance §5.3"],
    )


def _minimal_context() -> DealContext:
    """A DealContext with only property basics — no analysis data."""
    return DealContext(
        property_address="123 Main St, Miami, FL 33101",
        municipality="Miami",
        county="Miami-Dade",
        state_code="FL",
        deal_type=DealType.land_deal,
    )


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------


class TestDealSummaryRegistry:
    def test_deal_summary_clauses_exist(self):
        registry = _registry()
        clauses = registry.get(DocumentType.deal_summary, DealType.land_deal)
        assert len(clauses) >= 7, f"Expected >=7 deal summary clauses, got {len(clauses)}"

    def test_deal_summary_has_property_overview(self):
        registry = _registry()
        clause = registry.get_by_id("deal_summary.property_overview")
        assert clause is not None
        assert DocumentType.deal_summary in clause.document_types

    def test_deal_summary_has_zoning_analysis(self):
        registry = _registry()
        clause = registry.get_by_id("deal_summary.zoning_analysis")
        assert clause is not None

    def test_deal_summary_has_risk_factors(self):
        registry = _registry()
        clause = registry.get_by_id("deal_summary.risk_factors")
        assert clause is not None

    def test_shared_plotlot_footer_included(self):
        """Shared clauses with deal_summary in document_types should be included."""
        registry = _registry()
        clauses = registry.get(DocumentType.deal_summary, DealType.land_deal)
        ids = {c.id for c in clauses}
        assert "shared.plotlot_footer" in ids


# ---------------------------------------------------------------------------
# Assembly pipeline
# ---------------------------------------------------------------------------


class TestDealSummaryAssembly:
    def test_full_context_includes_all_sections(self):
        """With full analysis data, all conditional clauses should be included."""
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary, deal_type=DealType.land_deal
        )
        context = _full_context()
        rendered = assemble_clauses(config, context, registry)

        ids = {r.id for r in rendered}
        assert "deal_summary.property_overview" in ids
        assert "deal_summary.zoning_analysis" in ids
        assert "deal_summary.density_breakdown" in ids
        assert "deal_summary.comparable_sales" in ids
        assert "deal_summary.proforma_summary" in ids
        assert "deal_summary.risk_factors" in ids
        assert "deal_summary.ai_recommendation" in ids

    def test_minimal_context_excludes_conditional_clauses(self):
        """With no analysis data, conditional clauses should be excluded."""
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary, deal_type=DealType.land_deal
        )
        context = _minimal_context()
        rendered = assemble_clauses(config, context, registry)

        ids = {r.id for r in rendered}
        # These have conditions that require data > 0
        assert "deal_summary.density_breakdown" not in ids
        assert "deal_summary.comparable_sales" not in ids
        assert "deal_summary.proforma_summary" not in ids
        assert "deal_summary.ai_recommendation" not in ids

    def test_minimal_context_includes_unconditional(self):
        """Property overview and zoning should always be included."""
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary, deal_type=DealType.land_deal
        )
        context = _minimal_context()
        rendered = assemble_clauses(config, context, registry)

        ids = {r.id for r in rendered}
        assert "deal_summary.property_overview" in ids
        assert "deal_summary.zoning_analysis" in ids
        assert "deal_summary.risk_factors" in ids

    def test_clauses_sorted_by_order_weight(self):
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary, deal_type=DealType.land_deal
        )
        context = _full_context()
        rendered = assemble_clauses(config, context, registry)

        weights = [r.order_weight for r in rendered]
        assert weights == sorted(weights), f"Clauses not sorted: {weights}"

    def test_rendered_content_contains_address(self):
        """Property overview should render the address from context."""
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary, deal_type=DealType.land_deal
        )
        context = _full_context()
        rendered = assemble_clauses(config, context, registry)

        overview = next(r for r in rendered if r.id == "deal_summary.property_overview")
        assert "7940 Plantation Blvd" in overview.rendered_content

    def test_rendered_content_contains_zoning_data(self):
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary, deal_type=DealType.land_deal
        )
        context = _full_context()
        rendered = assemble_clauses(config, context, registry)

        zoning = next(r for r in rendered if r.id == "deal_summary.zoning_analysis")
        assert "RS-4" in zoning.rendered_content

    def test_rendered_content_contains_max_units(self):
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary, deal_type=DealType.land_deal
        )
        context = _full_context()
        rendered = assemble_clauses(config, context, registry)

        density = next(r for r in rendered if r.id == "deal_summary.density_breakdown")
        assert "4" in density.rendered_content

    def test_rendered_ai_recommendation(self):
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary, deal_type=DealType.land_deal
        )
        context = _full_context()
        rendered = assemble_clauses(config, context, registry)

        ai = next(r for r in rendered if r.id == "deal_summary.ai_recommendation")
        assert "Strong development potential" in ai.rendered_content


# ---------------------------------------------------------------------------
# Docx output
# ---------------------------------------------------------------------------


class TestDealSummaryDocx:
    def test_generates_valid_docx(self):
        """End-to-end: assemble a deal summary and verify .docx bytes."""
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary,
            deal_type=DealType.land_deal,
            output_format="docx",
        )
        context = _full_context()
        doc = assemble_document(config, context, registry)

        assert doc.data[:4] == b"PK\x03\x04"  # ZIP/docx magic bytes
        assert doc.filename.startswith("DEAL_SUMMARY_")
        assert doc.filename.endswith(".docx")
        assert (
            doc.content_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert len(doc.data) > 1000  # non-trivial document

    def test_minimal_docx_still_valid(self):
        """Even with minimal context, the document should be valid."""
        registry = _registry()
        config = AssemblyConfig(
            document_type=DocumentType.deal_summary,
            deal_type=DealType.land_deal,
            output_format="docx",
        )
        context = _minimal_context()
        doc = assemble_document(config, context, registry)

        assert doc.data[:4] == b"PK\x03\x04"
        assert len(doc.data) > 500
