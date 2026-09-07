"""Tests for clause-engine reference-data fixes (bugs 7 & 8).

Bug 7: _state_variants.yaml (50-state terminology) and _categories.yaml were
loaded into the registry but never consumed/enforced.
Bug 8: the seller-finance PSA purchase-price clause required
financing_type=='seller_carryback', so a seller_finance deal with no explicit
financing_type produced a PSA with no purchase-price section.
"""

from plotlot.clauses.engine import assemble_clauses
from plotlot.clauses.loader import ClauseRegistry
from plotlot.clauses.schema import AssemblyConfig, DealContext, DealType, DocumentType

_REGISTRY = ClauseRegistry.from_directory()


def _assemble(state_code: str, financing_type: str = "") -> list:
    config = AssemblyConfig(
        document_type=DocumentType.psa,
        deal_type=DealType.seller_finance,
        state_code=state_code,
    )
    ctx = DealContext(deal_type=DealType.seller_finance, financing_type=financing_type)
    return assemble_clauses(config, ctx, _REGISTRY)


class TestSellerFinanceCondition:
    def test_seller_finance_psa_includes_price_without_financing_type(self):
        # Bug 8: financing_type unset must still yield a purchase-price section.
        ids = [c.id for c in _assemble("CA", financing_type="")]
        assert "psa.purchase_price_seller_finance" in ids

    def test_explicit_seller_carryback_still_works(self):
        ids = [c.id for c in _assemble("CA", financing_type="seller_carryback")]
        assert "psa.purchase_price_seller_finance" in ids

    def test_natural_seller_finance_value_works(self):
        ids = [c.id for c in _assemble("CA", financing_type="seller_finance")]
        assert "psa.purchase_price_seller_finance" in ids


class TestStateTerminology:
    def _price_clause_text(self, state_code: str) -> str:
        clauses = _assemble(state_code)
        clause = next(c for c in clauses if c.id == "psa.purchase_price_seller_finance")
        return clause.rendered_content

    def test_california_uses_land_contract(self):
        assert "Land Contract" in self._price_clause_text("CA")

    def test_texas_uses_contract_for_deed(self):
        assert "Contract for Deed" in self._price_clause_text("TX")

    def test_registry_loaded_terminology(self):
        # The reference file must actually be loaded (bug 7).
        assert _REGISTRY.state_terminology.get("CA") == "Land Contract"
        assert _REGISTRY.state_terminology.get("TX") == "Contract for Deed"


class TestCategoryRangesEnforced:
    def test_categories_loaded(self):
        assert _REGISTRY.categories  # _categories.yaml loaded into the registry

    def test_contract_clause_weights_within_category_ranges(self):
        """LOI/PSA clauses must fall in their category's order range.

        The _categories scheme governs the legal contracts; proforma clauses use
        an independent ordering (the xlsx renderer builds its own sheets), so they
        are out of scope here.
        """
        cats = _REGISTRY.categories
        contract_docs = {DocumentType.loi, DocumentType.psa}
        offenders = []
        for clause in _REGISTRY.all_clauses:
            if not contract_docs & set(clause.document_types):
                continue
            cat = cats.get(clause.category)
            if not cat:
                continue
            lo, hi = cat["order_range"]
            if not (lo <= clause.order_weight <= hi):
                offenders.append((clause.id, str(clause.category), clause.order_weight, lo, hi))
        assert not offenders, f"order_weight outside category range: {offenders}"
