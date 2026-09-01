"""Tests for conservative, evidence-backed acquisition decision packets."""

from __future__ import annotations

from datetime import date, datetime, timezone

from plotlot.application.market.comps import qualify_comps
from plotlot.application.market.decision import build_acquisition_decision
from plotlot.application.market.models import (
    AcquisitionDecisionInputs,
    AcquisitionDecisionStatus,
    ComparableSale,
    ComparableSource,
    CompPolicy,
    SubjectProperty,
)


def _qualified_comps():
    subject = SubjectProperty(
        address="100 Main St, Miramar, FL",
        latitude=25.99,
        longitude=-80.23,
        property_type="land",
        lot_size_sqft=10_000,
    )
    prices = [500_000, 520_000, 540_000, 560_000, 580_000]
    sales = [
        ComparableSale(
            sale_id=f"sale-{index}",
            address=f"{index} Comp St, Miramar, FL",
            sale_price=price,
            sale_date=date(2026, 3, index + 1),
            latitude=25.99 + index * 0.001,
            longitude=-80.23,
            property_type="land",
            lot_size_sqft=10_000,
            source=ComparableSource(
                provider="county_recorder" if index % 2 == 0 else "mls",
                record_id=f"record-{index}",
                source_url=f"https://example.test/{index}",
                retrieved_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
            ),
            evidence_id=f"ev_{index}",
        )
        for index, price in enumerate(prices)
    ]
    return qualify_comps(
        subject,
        sales,
        CompPolicy(),
        as_of=date(2026, 9, 1),
    )


def test_decision_uses_lower_of_comp_floor_and_residual_ceiling():
    decision = build_acquisition_decision(
        AcquisitionDecisionInputs(
            purchase_price=450_000,
            comps=_qualified_comps(),
            residual_land_value=600_000,
        )
    )

    assert decision.status == AcquisitionDecisionStatus.ADVANCE_FOR_REVIEW
    assert decision.supported_basis == decision.comp_floor
    assert decision.supported_basis < decision.residual_ceiling
    assert decision.cushion_dollars == decision.supported_basis - 450_000
    assert decision.cushion_percent > 0
    assert decision.evidence_ids == ("ev_0", "ev_1", "ev_2", "ev_3", "ev_4")


def test_decision_rejects_price_above_conservative_supported_basis():
    decision = build_acquisition_decision(
        AcquisitionDecisionInputs(
            purchase_price=700_000,
            comps=_qualified_comps(),
            residual_land_value=800_000,
        )
    )

    assert decision.status == AcquisitionDecisionStatus.REJECT_BUY_BOX
    assert decision.cushion_dollars < 0
    assert "exceeds" in " ".join(decision.reasons).lower()


def test_decision_holds_when_price_has_no_modeled_cushion():
    comps = _qualified_comps()
    assert comps.valuation_low is not None

    decision = build_acquisition_decision(
        AcquisitionDecisionInputs(
            purchase_price=comps.valuation_low,
            comps=comps,
            residual_land_value=comps.valuation_low + 50_000,
        )
    )

    assert decision.status == AcquisitionDecisionStatus.HOLD_FOR_INPUTS
    assert decision.cushion_dollars == 0


def test_decision_never_advances_without_explicit_price():
    decision = build_acquisition_decision(
        AcquisitionDecisionInputs(
            purchase_price=None,
            comps=_qualified_comps(),
            residual_land_value=600_000,
        )
    )

    assert decision.status == AcquisitionDecisionStatus.HOLD_FOR_INPUTS
    assert decision.supported_basis is not None
    assert decision.cushion_dollars is None


def test_decision_abstains_without_both_comps_and_residual_support():
    comps = _qualified_comps()

    no_residual = build_acquisition_decision(
        AcquisitionDecisionInputs(
            purchase_price=450_000,
            comps=comps,
            residual_land_value=None,
        )
    )
    assert no_residual.status == AcquisitionDecisionStatus.INSUFFICIENT_EVIDENCE

    insufficient_comps = qualify_comps(
        SubjectProperty(
            address="100 Main St, Miramar, FL",
            latitude=25.99,
            longitude=-80.23,
            property_type="land",
            lot_size_sqft=10_000,
        ),
        [],
        CompPolicy(),
        as_of=date(2026, 9, 1),
    )
    no_comps = build_acquisition_decision(
        AcquisitionDecisionInputs(
            purchase_price=450_000,
            comps=insufficient_comps,
            residual_land_value=600_000,
        )
    )
    assert no_comps.status == AcquisitionDecisionStatus.INSUFFICIENT_EVIDENCE
