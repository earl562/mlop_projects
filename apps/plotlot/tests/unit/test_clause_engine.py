"""Tests for the clause assembly engine."""

from pathlib import Path

import yaml

from plotlot.clauses.engine import (
    assemble_clauses,
    assemble_document,
    evaluate_condition,
    render_clause,
    resolve_groups,
)
from plotlot.clauses.loader import ClauseRegistry
from plotlot.clauses.schema import (
    AssemblyConfig,
    ClauseCategory,
    ContractClause,
    DealContext,
    DealType,
    DocumentType,
)


def _clause(
    clause_id: str,
    order: int = 100,
    group_id: str | None = None,
    condition: str | None = None,
    template: str = "Default content",
    deal_types: list[DealType] | None = None,
    doc_types: list[DocumentType] | None = None,
) -> ContractClause:
    return ContractClause(
        id=clause_id,
        category=ClauseCategory.financial_terms,
        title=f"Test {clause_id}",
        deal_types=deal_types or list(DealType),
        document_types=doc_types or [DocumentType.loi],
        order_weight=order,
        content_template=template,
        group_id=group_id,
        condition_expr=condition,
    )


# ---------------------------------------------------------------------------
# evaluate_condition
# ---------------------------------------------------------------------------


class TestEvaluateCondition:
    def test_string_equality(self):
        ctx = DealContext(financing_type="subject_to")
        assert evaluate_condition("context.financing_type == 'subject_to'", ctx) is True
        assert evaluate_condition("context.financing_type == 'wrap'", ctx) is False

    def test_string_inequality(self):
        ctx = DealContext(financing_type="wrap")
        assert evaluate_condition("context.financing_type != 'subject_to'", ctx) is True

    def test_numeric_greater_than(self):
        ctx = DealContext(purchase_price=500_000)
        assert evaluate_condition("context.purchase_price > 0", ctx) is True
        assert evaluate_condition("context.purchase_price > 1000000", ctx) is False

    def test_numeric_equality(self):
        ctx = DealContext(max_units=4)
        assert evaluate_condition("context.max_units == 4", ctx) is True

    def test_in_operator(self):
        ctx = DealContext(financing_type="subject_to")
        assert (
            evaluate_condition("context.financing_type in ['subject_to', 'wrap', 'hybrid']", ctx)
            is True
        )
        assert (
            evaluate_condition("context.financing_type in ['cash', 'conventional']", ctx) is False
        )

    def test_missing_field(self):
        ctx = DealContext()
        assert evaluate_condition("context.nonexistent_field == 'value'", ctx) is False

    def test_unparseable_returns_true(self):
        ctx = DealContext()
        assert evaluate_condition("some garbage expression", ctx) is True

    def test_empty_string_field(self):
        ctx = DealContext(seller_broker_name="")
        assert evaluate_condition("context.seller_broker_name != ''", ctx) is False

    def test_empty_in_list_returns_false(self):
        """Empty in list [] should always return False, never match."""
        ctx = DealContext(financing_type="subject_to")
        assert evaluate_condition("context.financing_type in []", ctx) is False

    def test_empty_in_list_with_empty_field(self):
        """Empty in list [] should return False even when field is empty string."""
        ctx = DealContext(financing_type="")
        assert evaluate_condition("context.financing_type in []", ctx) is False

    def test_boolean_field_true(self):
        """Boolean field == True evaluates correctly."""
        ctx = DealContext(financing_contingency=True)
        assert evaluate_condition("context.financing_contingency == True", ctx) is True

    def test_numeric_vs_string_mismatch(self):
        """Comparing a string field with > numeric operator should not crash."""
        ctx = DealContext(buyer_name="Earl")
        # float("Earl") fails, falls through to string comparison.
        # str("Earl") > "100" is True (lexicographic: "E" > "1").
        # The key assertion is that it does not raise an exception.
        result = evaluate_condition("context.buyer_name > 100", ctx)
        assert isinstance(result, bool)

    def test_zero_value_greater_than(self):
        """max_units=0 is not > 0."""
        ctx = DealContext(max_units=0)
        assert evaluate_condition("context.max_units > 0", ctx) is False

    def test_negative_value_greater_than(self):
        """Positive price is greater than -1."""
        ctx = DealContext(purchase_price=100)
        assert evaluate_condition("context.purchase_price > -1", ctx) is True

    def test_numeric_greater_equal(self):
        """max_units >= 50 with max_units=50 is True (boundary)."""
        ctx = DealContext(max_units=50)
        assert evaluate_condition("context.max_units >= 50", ctx) is True

    def test_numeric_less_than(self):
        """max_units < 10 with max_units=5 is True."""
        ctx = DealContext(max_units=5)
        assert evaluate_condition("context.max_units < 10", ctx) is True


# ---------------------------------------------------------------------------
# resolve_groups
# ---------------------------------------------------------------------------


class TestResolveGroups:
    def test_no_groups_passthrough(self):
        clauses = [_clause("a"), _clause("b")]
        ctx = DealContext()
        result = resolve_groups(clauses, ctx)
        assert len(result) == 2

    def test_selects_matching_group_member(self):
        clauses = [
            _clause("ungrouped"),
            _clause("mirror", group_id="fin", condition="context.financing_type == 'subject_to'"),
            _clause("hybrid", group_id="fin", condition="context.financing_type == 'hybrid'"),
            _clause(
                "carryback",
                group_id="fin",
                condition="context.financing_type == 'seller_carryback'",
            ),
        ]
        ctx = DealContext(financing_type="hybrid")
        result = resolve_groups(clauses, ctx)
        ids = {c.id for c in result}
        assert "ungrouped" in ids
        assert "hybrid" in ids
        assert "mirror" not in ids
        assert "carryback" not in ids

    def test_no_match_excludes_group(self):
        clauses = [
            _clause("mirror", group_id="fin", condition="context.financing_type == 'subject_to'"),
        ]
        ctx = DealContext(financing_type="cash")
        result = resolve_groups(clauses, ctx)
        assert len(result) == 0

    def test_default_member_no_condition(self):
        clauses = [
            _clause("conditional", group_id="g", condition="context.financing_type == 'nope'"),
            _clause("default", group_id="g"),  # no condition = fallback
        ]
        ctx = DealContext(financing_type="something_else")
        result = resolve_groups(clauses, ctx)
        assert len(result) == 1
        assert result[0].id == "default"

    def test_all_members_fail_excludes_group(self):
        """When every member in a group has a failing condition, the group is excluded."""
        clauses = [
            _clause("ungrouped"),
            _clause("opt_a", group_id="g", condition="context.financing_type == 'a'"),
            _clause("opt_b", group_id="g", condition="context.financing_type == 'b'"),
            _clause("opt_c", group_id="g", condition="context.financing_type == 'c'"),
        ]
        ctx = DealContext(financing_type="none_of_these")
        result = resolve_groups(clauses, ctx)
        ids = {c.id for c in result}
        assert ids == {"ungrouped"}

    def test_multiple_defaults_first_wins(self):
        """When multiple group members have no condition, the first one wins."""
        clauses = [
            _clause("default_1", group_id="g"),
            _clause("default_2", group_id="g"),
        ]
        ctx = DealContext()
        result = resolve_groups(clauses, ctx)
        assert len(result) == 1
        assert result[0].id == "default_1"

    def test_single_member_group(self):
        """A group with only one member works normally (condition evaluated)."""
        clauses = [
            _clause("solo", group_id="g", condition="context.financing_type == 'wrap'"),
        ]
        ctx = DealContext(financing_type="wrap")
        result = resolve_groups(clauses, ctx)
        assert len(result) == 1
        assert result[0].id == "solo"


# ---------------------------------------------------------------------------
# render_clause
# ---------------------------------------------------------------------------


class TestRenderClause:
    def test_basic_render(self):
        clause = _clause("test", template="Price: {{ context.purchase_price|currency }}")
        ctx = DealContext(purchase_price=500_000)
        rendered = render_clause(clause, ctx)
        assert rendered.id == "test"
        assert "$500,000" in rendered.rendered_content

    def test_missing_variable_renders_empty(self):
        clause = _clause("test", template="Buyer: {{ context.buyer_name }}")
        ctx = DealContext()  # buyer_name defaults to ""
        rendered = render_clause(clause, ctx)
        assert "Buyer:" in rendered.rendered_content

    def test_state_variant(self):
        clause = _clause(
            "test",
            template="Default: Agreement for Sale",
        )
        clause.state_variants = {"TX": "Texas: Contract for Deed"}
        ctx = DealContext()
        rendered = render_clause(clause, ctx, state_code="TX")
        assert "Contract for Deed" in rendered.rendered_content

    def test_state_variant_not_matched(self):
        clause = _clause("test", template="Default template")
        clause.state_variants = {"TX": "Texas override"}
        ctx = DealContext()
        rendered = render_clause(clause, ctx, state_code="FL")
        assert "Default template" in rendered.rendered_content

    def test_empty_template_renders_empty(self):
        """An empty content template renders to an empty string."""
        clause = _clause("test", template="")
        ctx = DealContext()
        rendered = render_clause(clause, ctx)
        assert rendered.rendered_content == ""

    def test_unicode_in_context(self):
        """Unicode characters in context fields render correctly."""
        clause = _clause("test", template="Buyer: {{ context.buyer_name }}")
        ctx = DealContext(buyer_name="José García")
        rendered = render_clause(clause, ctx)
        assert "José García" in rendered.rendered_content

    def test_currency_filter(self):
        """Currency filter formats purchase_price as $500,000."""
        clause = _clause("test", template="{{ context.purchase_price|currency }}")
        ctx = DealContext(purchase_price=500_000)
        rendered = render_clause(clause, ctx)
        assert rendered.rendered_content == "$500,000"

    def test_currency_filter_zero(self):
        """Currency filter with 0 renders as $0."""
        clause = _clause("test", template="{{ context.purchase_price|currency }}")
        ctx = DealContext(purchase_price=0)
        rendered = render_clause(clause, ctx)
        assert rendered.rendered_content == "$0"


# ---------------------------------------------------------------------------
# assemble_clauses
# ---------------------------------------------------------------------------


def _build_test_registry(tmp_path: Path) -> ClauseRegistry:
    """Build a registry with LOI test clauses."""
    clauses = [
        {
            "id": "loi.header",
            "category": "party_identification",
            "title": "Header",
            "document_types": ["loi"],
            "order_weight": 100,
            "content_template": "Dear {{ context.seller_name or '[SELLER]' }}",
        },
        {
            "id": "loi.price",
            "category": "financial_terms",
            "title": "Purchase Price",
            "document_types": ["loi"],
            "order_weight": 300,
            "content_template": "Price: {{ context.purchase_price|currency }}",
        },
        {
            "id": "loi.mirror",
            "category": "financial_terms",
            "title": "Mirror Financing",
            "document_types": ["loi"],
            "deal_types": ["subject_to", "wrap"],
            "order_weight": 320,
            "group_id": "financing_type",
            "condition_expr": "context.financing_type == 'subject_to'",
            "content_template": "Mirror existing loan of {{ context.existing_mortgage_balance_1|currency }}",
        },
        {
            "id": "loi.hybrid",
            "category": "financial_terms",
            "title": "Hybrid Financing",
            "document_types": ["loi"],
            "deal_types": ["hybrid", "wrap"],
            "order_weight": 320,
            "group_id": "financing_type",
            "condition_expr": "context.financing_type == 'hybrid'",
            "content_template": "Hybrid: existing plus {{ context.additional_principal|currency }}",
        },
        {
            "id": "loi.signatures",
            "category": "signatures",
            "title": "Signatures",
            "document_types": ["loi"],
            "order_weight": 1000,
            "content_template": "Signed by {{ context.buyer_name or '[BUYER]' }}",
        },
    ]

    defs_dir = tmp_path / "definitions"
    defs_dir.mkdir()
    for c in clauses:
        path = defs_dir / f"{c['id'].replace('.', '_')}.yaml"
        with open(path, "w") as f:
            yaml.dump(c, f)

    return ClauseRegistry.from_directory(defs_dir)


class TestAssembleClauses:
    def test_assembles_loi_land_deal(self, tmp_path):
        registry = _build_test_registry(tmp_path)
        config = AssemblyConfig(document_type=DocumentType.loi, deal_type=DealType.land_deal)
        ctx = DealContext(
            seller_name="John Doe",
            purchase_price=500_000,
            buyer_name="Earl Perry",
        )
        result = assemble_clauses(config, ctx, registry)
        # Should include header, price, signatures (not financing — land_deal not in mirror/hybrid deal_types)
        ids = [r.id for r in result]
        assert "loi.header" in ids
        assert "loi.price" in ids
        assert "loi.signatures" in ids
        assert "loi.mirror" not in ids

    def test_assembles_loi_subject_to(self, tmp_path):
        registry = _build_test_registry(tmp_path)
        config = AssemblyConfig(document_type=DocumentType.loi, deal_type=DealType.subject_to)
        ctx = DealContext(
            financing_type="subject_to",
            existing_mortgage_balance_1=350_000,
        )
        result = assemble_clauses(config, ctx, registry)
        ids = [r.id for r in result]
        assert "loi.mirror" in ids
        assert "loi.hybrid" not in ids

    def test_sorted_by_order_weight(self, tmp_path):
        registry = _build_test_registry(tmp_path)
        config = AssemblyConfig(document_type=DocumentType.loi)
        ctx = DealContext()
        result = assemble_clauses(config, ctx, registry)
        weights = [r.order_weight for r in result]
        assert weights == sorted(weights)

    def test_exclude_clause_ids(self, tmp_path):
        registry = _build_test_registry(tmp_path)
        config = AssemblyConfig(
            document_type=DocumentType.loi,
            exclude_clause_ids=["loi.price"],
        )
        ctx = DealContext()
        result = assemble_clauses(config, ctx, registry)
        ids = [r.id for r in result]
        assert "loi.price" not in ids

    def test_renders_template_content(self, tmp_path):
        registry = _build_test_registry(tmp_path)
        config = AssemblyConfig(document_type=DocumentType.loi)
        ctx = DealContext(seller_name="Jane Smith", purchase_price=750_000)
        result = assemble_clauses(config, ctx, registry)
        header = next(r for r in result if r.id == "loi.header")
        assert "Jane Smith" in header.rendered_content
        price = next(r for r in result if r.id == "loi.price")
        assert "$750,000" in price.rendered_content


# ---------------------------------------------------------------------------
# assemble_document (end-to-end docx)
# ---------------------------------------------------------------------------


class TestAssembleDocument:
    def test_generates_docx(self, tmp_path):
        registry = _build_test_registry(tmp_path)
        config = AssemblyConfig(
            document_type=DocumentType.loi,
            output_format="docx",
        )
        ctx = DealContext(
            property_address="7940 Plantation Blvd, Miramar, FL 33023",
            buyer_name="Earl Perry",
            purchase_price=500_000,
        )
        doc = assemble_document(config, ctx, registry)
        assert doc.filename.startswith("LOI_")
        assert doc.filename.endswith(".docx")
        assert doc.content_type.endswith("wordprocessingml.document")
        # .docx files start with PK (zip format)
        assert doc.data[:2] == b"PK"
        assert len(doc.data) > 100

    def test_unsupported_format_raises(self, tmp_path):
        registry = _build_test_registry(tmp_path)
        config = AssemblyConfig(
            document_type=DocumentType.loi,
            output_format="pdf",
        )
        ctx = DealContext()
        try:
            assemble_document(config, ctx, registry)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Unsupported" in str(e)
