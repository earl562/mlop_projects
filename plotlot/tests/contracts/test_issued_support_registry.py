from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from plotlot.domain.issued_support_registry import parse_issued_support_registry
from plotlot.domain.opportunity_contract import (
    evaluate_opportunity_decision,
    parse_opportunity_decision_input,
)
from tests.contracts.contract_test_support import decision_payload, issued_registry_payload

EVALUATED_AT = datetime(2026, 7, 25, tzinfo=UTC)


def test_blocks_coordinate_shaped_but_unissued_64f_forgery() -> None:
    payload = decision_payload()
    for receipt in payload["support"]["coordinateReceipts"]:
        receipt["evidenceReceiptId"] = (
            f"support:miami-dade:miami:{receipt['workflow']}:{receipt['factFamily']}:{'f' * 64}"
        )

    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(json.dumps(payload)),
        receipt_registry=parse_issued_support_registry(json.dumps(issued_registry_payload())),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "blocked"
    assert result.recommendation == "abstain"
    assert result.verified_ceiling_cents is None
    assert result.blocker_codes == ("support-receipt-unissued",)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"revokedAt": "2026-07-24T00:00:00Z"}, "support-receipt-revoked"),
        ({"expiresAt": "2026-07-24T00:00:00Z"}, "support-receipt-expired"),
        ({"issuedAt": "2026-07-26T00:00:00Z"}, "support-receipt-not-yet-issued"),
    ],
)
def test_blocks_inactive_issued_receipts(change: dict[str, str], expected: str) -> None:
    registry_payload = issued_registry_payload()
    registry_payload["receipts"][0].update(change)
    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(json.dumps(decision_payload())),
        receipt_registry=parse_issued_support_registry(json.dumps(registry_payload)),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "blocked"
    assert result.blocker_codes == (expected,)


def test_blocks_receipt_rebound_to_another_coordinate() -> None:
    payload = decision_payload()
    payload["support"]["coordinateReceipts"][0]["evidenceReceiptId"] = payload["support"][
        "coordinateReceipts"
    ][1]["evidenceReceiptId"]
    payload["support"]["coordinateReceipts"][1]["evidenceReceiptId"] = "unissued-replacement"
    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(json.dumps(payload)),
        receipt_registry=parse_issued_support_registry(json.dumps(issued_registry_payload())),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "blocked"
    assert set(result.blocker_codes) == {
        "support-receipt-rebound",
        "support-receipt-unissued",
    }


@pytest.mark.parametrize("field", ["issuerId", "keyVersion", "schemaVersion"])
def test_rejects_unknown_registry_authority_or_version(field: str) -> None:
    payload = issued_registry_payload()
    if field == "schemaVersion":
        payload[field] = "IssuedSupportRegistryV999"
    else:
        payload["receipts"][0][field] = "unknown"

    with pytest.raises(ValidationError):
        parse_issued_support_registry(json.dumps(payload))


@pytest.mark.parametrize("field", ["receiptId", "coordinate"])
def test_rejects_duplicate_registry_entries(field: str) -> None:
    payload = issued_registry_payload()
    duplicate = dict(payload["receipts"][0])
    if field == "coordinate":
        duplicate["receiptId"] = "different-issued-id"
    payload["receipts"].append(duplicate)

    with pytest.raises(ValidationError):
        parse_issued_support_registry(json.dumps(payload))
