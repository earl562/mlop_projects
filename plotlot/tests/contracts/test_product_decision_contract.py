from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from plotlot.domain.opportunity_contract import (
    evaluate_opportunity_decision,
    parse_opportunity_decision_input,
    parse_opportunity_decision_projection,
    product_contract_projection,
    product_contract_projection_hash,
)
from plotlot.domain.issued_support_registry import parse_issued_support_registry
from tests.contracts.contract_test_support import (
    JsonValue,
    decision_payload,
    issued_registry_payload,
    support_payload,
)

REGISTRY = parse_issued_support_registry(json.dumps(issued_registry_payload()))
EVALUATED_AT = datetime(2026, 7, 25, tzinfo=UTC)


def evaluate(payload: dict[str, JsonValue]):
    parsed = parse_opportunity_decision_input(json.dumps(payload))
    return evaluate_opportunity_decision(
        parsed,
        receipt_registry=REGISTRY,
        evaluated_at=EVALUATED_AT,
    )


def test_releases_accepted_decision_at_verified_ceiling() -> None:
    result = evaluate(decision_payload())

    assert result.status == "released"
    assert result.recommendation == "control"
    assert result.verified_ceiling_cents == 52_500_000
    assert result.release == "released"


def test_keeps_complete_unrequested_decision_provisional() -> None:
    result = evaluate(decision_payload(requested_release=False))

    assert result.status == "provisional"
    assert result.pricing == "evidence-supported"
    assert result.release == "eligible"


@pytest.mark.parametrize(
    ("field", "value", "expected_status"),
    [
        ("identity", "ambiguous", "blocked"),
        ("local_truth", "stale", "blocked"),
        ("capacity", "conflict", "blocked"),
        ("market", "thin", "provisional"),
        ("market", "stale", "blocked"),
        ("underwriting", "conflict", "blocked"),
        ("support", "unsupported", "blocked"),
    ],
)
def test_abstains_for_unready_or_outside_coverage(
    field: str,
    value: str,
    expected_status: str,
) -> None:
    result = evaluate(decision_payload(**{field: value}))

    assert result.status == expected_status
    assert result.verified_ceiling_cents is None
    assert result.recommendation == "abstain"


def test_rejects_absent_persona() -> None:
    payload = decision_payload()
    del payload["persona"]

    with pytest.raises(ValidationError):
        parse_opportunity_decision_input(json.dumps(payload))


def test_rejects_self_reported_readiness() -> None:
    payload = decision_payload()
    payload["readiness"] = "ready"

    with pytest.raises(ValidationError):
        parse_opportunity_decision_input(json.dumps(payload))


def test_rejects_price_without_evidence() -> None:
    payload = {
        "schemaVersion": "OpportunityDecisionProjectionV1",
        "processing": "complete",
        "readiness": "blocked",
        "pricing": "evidence-supported",
        "review": "approved",
        "release": "released",
        "status": "released",
        "recommendation": "control",
        "verifiedCeilingCents": 52_500_000,
        "evidenceReceiptIds": [],
        "blockerCodes": [],
    }

    with pytest.raises(ValidationError):
        parse_opportunity_decision_projection(json.dumps(payload))


def test_rejects_status_widening() -> None:
    payload = {
        "schemaVersion": "OpportunityDecisionProjectionV1",
        "processing": "complete",
        "readiness": "blocked",
        "pricing": "unpriced",
        "review": "unreviewed",
        "release": "blocked",
        "status": "released",
        "recommendation": "abstain",
        "verifiedCeilingCents": None,
        "evidenceReceiptIds": [],
        "blockerCodes": ["outside-coverage"],
    }

    with pytest.raises(ValidationError):
        parse_opportunity_decision_projection(json.dumps(payload))


def test_rejects_provisional_release_and_recommendation_widening() -> None:
    payload = {
        "schemaVersion": "OpportunityDecisionProjectionV1",
        "processing": "not-started",
        "readiness": "blocked",
        "pricing": "unpriced",
        "review": "unreviewed",
        "release": "eligible",
        "status": "provisional",
        "recommendation": "control",
        "verifiedCeilingCents": None,
        "evidenceReceiptIds": [],
        "blockerCodes": [],
    }

    with pytest.raises(ValidationError):
        parse_opportunity_decision_projection(json.dumps(payload))


def test_disabled_broward_lane_cannot_release_with_forged_support() -> None:
    payload = decision_payload()
    payload["opportunity"]["county"] = "broward"
    payload["opportunity"]["municipalityLane"] = "fort-lauderdale"
    payload["support"] = support_payload("broward", "fort-lauderdale")

    result = evaluate(payload)

    assert result.status == "blocked"
    assert result.blocker_codes == ("county-disabled", "support-receipt-unissued")


def test_rejects_opportunity_lane_county_mismatch() -> None:
    payload = decision_payload()
    payload["opportunity"]["county"] = "broward"

    with pytest.raises(ValidationError):
        parse_opportunity_decision_input(json.dumps(payload))


def test_rejects_duplicate_support_receipts_and_blocks_cross_coordinate_rebinding() -> None:
    duplicate = decision_payload()
    receipts = duplicate["support"]["coordinateReceipts"]
    receipts[1]["evidenceReceiptId"] = receipts[0]["evidenceReceiptId"]
    with pytest.raises(ValidationError):
        parse_opportunity_decision_input(json.dumps(duplicate))

    crossed = decision_payload()
    crossed["support"]["coordinateReceipts"][0]["evidenceReceiptId"] = (
        f"support:miami-dade:miami:decision-release:reviewer-approval:{'b' * 64}"
    )
    result = evaluate(crossed)
    assert result.status == "blocked"
    assert result.blocker_codes == ("support-receipt-unissued",)


def test_contract_projection_freezes_persona_release_and_external_boundaries() -> None:
    projection = product_contract_projection()

    assert projection.decision_question == "pursue-or-control-at-verified-ceiling"
    assert projection.private_beta_policy.initial_county == "miami-dade"
    assert projection.private_beta_policy.disabled_counties == ("broward", "palm-beach")
    assert projection.private_beta_policy.county_boolean_implies_coverage is False
    assert "seller-contact" in projection.external_action_boundary.disabled
    assert product_contract_projection_hash() == (
        "ab82ad9aaebc10b32535ae89556f772827b00b72ef90a55cec2553b0ddab033f"
    )
