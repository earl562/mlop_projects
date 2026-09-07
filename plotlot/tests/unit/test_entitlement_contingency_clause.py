"""Tests for the entitlement / rezoning contingency clauses (PSA + LOI).

This is the contract mechanism for the land developer's value-creation play:
control the parcel cheaply, then create value by rezoning/subdividing BEFORE
closing (see pipeline/upzoning.py for the engine that quantifies the upside).
The clause must be OFF by default and only assemble when the buyer opts into an
entitlement contingency, and it must spell out the contingent close, long pursuit
period, extension option, and seller-as-record-owner cooperation.
"""

from __future__ import annotations

from plotlot.clauses.engine import assemble_clauses
from plotlot.clauses.loader import ClauseRegistry
from plotlot.clauses.schema import AssemblyConfig, DealContext, DealType, DocumentType

_REGISTRY = ClauseRegistry.from_directory()


def _assemble(doc_type: DocumentType, ctx: DealContext) -> list:
    config = AssemblyConfig(document_type=doc_type, deal_type=DealType.land_deal, state_code="CA")
    return assemble_clauses(config, ctx, _REGISTRY)


def _entitlement_ctx() -> DealContext:
    return DealContext(
        deal_type=DealType.land_deal,
        entitlement_contingency=True,
        upzoning_vehicle="special use permit",
        entitlement_close_days=365,
        entitlement_extension_days=180,
        feasibility_days=90,
        target_units=12,
    )


def test_clauses_load_in_registry():
    assert _REGISTRY.get_by_id("psa.entitlement_contingency") is not None
    assert _REGISTRY.get_by_id("loi.entitlement_contingency") is not None


def test_excluded_by_default():
    """Off unless the buyer opts in — a normal land deal must not carry it."""
    psa_ids = [c.id for c in _assemble(DocumentType.psa, DealContext(deal_type=DealType.land_deal))]
    loi_ids = [c.id for c in _assemble(DocumentType.loi, DealContext(deal_type=DealType.land_deal))]
    assert "psa.entitlement_contingency" not in psa_ids
    assert "loi.entitlement_contingency" not in loi_ids


def test_psa_included_and_rendered_when_opted_in():
    clauses = _assemble(DocumentType.psa, _entitlement_ctx())
    clause = next((c for c in clauses if c.id == "psa.entitlement_contingency"), None)
    assert clause is not None
    text = clause.rendered_content
    # The contingent close, the vehicle, the long pursuit + extension, target yield.
    assert "special use permit" in text
    assert "contingent" in text.lower()
    assert "365 days" in text
    assert "180 days" in text
    assert "90-day feasibility" in text
    assert "12 units/lots" in text
    # Seller signs as record owner (the video's full-disclosure requirement).
    assert "record owner" in text
    assert "Deposit shall be returned to Buyer" in text


def test_loi_included_and_rendered_when_opted_in():
    clauses = _assemble(DocumentType.loi, _entitlement_ctx())
    clause = next((c for c in clauses if c.id == "loi.entitlement_contingency"), None)
    assert clause is not None
    text = clause.rendered_content
    assert "special use permit" in text
    assert "365 days" in text
    assert "record owner" in text


def test_template_falls_back_without_optional_fields():
    """With the flag on but no vehicle/days/target, sensible defaults render (no [TBD])."""
    ctx = DealContext(deal_type=DealType.land_deal, entitlement_contingency=True)
    clause = next(
        c for c in _assemble(DocumentType.psa, ctx) if c.id == "psa.entitlement_contingency"
    )
    text = clause.rendered_content
    assert "rezoning / upzoning approval" in text  # vehicle fallback
    assert "365 days" in text  # close-days fallback
    assert "180 days" in text  # extension fallback
    assert "Buyer's intended development" in text  # target-units fallback
    assert "[TBD]" not in text


def test_order_weight_in_contingencies_range():
    for cid in ("psa.entitlement_contingency", "loi.entitlement_contingency"):
        clause = _REGISTRY.get_by_id(cid)
        assert clause is not None
        assert 400 <= clause.order_weight <= 499
