from __future__ import annotations

import json
from copy import copy, deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from weakref import WeakKeyDictionary

import pytest
from pydantic import ValidationError

import plotlot.domain.issued_support_registry as issued_support_registry
from plotlot.domain.issued_support_registry import (
    IssuedSupportRegistryDocument,
    VerifiedIssuedSupportRegistry,
    parse_issued_support_registry,
)
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
    ("state", "evaluated_at", "expected"),
    [
        ("revoked", EVALUATED_AT, "support-receipt-revoked"),
        ("expired", datetime(2027, 7, 2, tzinfo=UTC), "support-receipt-expired"),
        ("future", datetime(2026, 6, 30, tzinfo=UTC), "support-receipt-not-yet-issued"),
    ],
)
def test_blocks_inactive_issued_receipts(state: str, evaluated_at: datetime, expected: str) -> None:
    registry_payload = issued_registry_payload()
    if state == "revoked":
        registry_payload["registryId"] = "plotlot-public-test-registry-revoked-2026-07-24"
        registry_payload["auditSha256"] = (
            "251c8b36f80a7d2ca792868900a75c8589334914a4257f36c69a392f1f271098"
        )
        registry_payload["receipts"][0]["revokedAt"] = "2026-07-24T00:00:00Z"
    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(json.dumps(decision_payload())),
        receipt_registry=parse_issued_support_registry(json.dumps(registry_payload)),
        evaluated_at=evaluated_at,
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


@pytest.mark.parametrize(
    "field",
    [
        "receipts",
        "_canonical_receipts",
        "_VerifiedIssuedSupportRegistry__receipts_by_id",
        "__dict__",
    ],
)
def test_verified_registry_is_opaque_and_slot_sealed(field: str) -> None:
    registry = parse_issued_support_registry(json.dumps(issued_registry_payload()))

    with pytest.raises(AttributeError):
        setattr(registry, field, "attacker")


def test_verified_registry_blocks_copy_update_and_serialization_apis() -> None:
    registry = parse_issued_support_registry(json.dumps(issued_registry_payload()))

    assert not hasattr(registry, "model_copy")
    assert not hasattr(registry, "model_dump")
    with pytest.raises(TypeError):
        copy(registry)
    with pytest.raises(TypeError):
        deepcopy(registry)
    with pytest.raises(TypeError):
        json.dumps(registry)


def test_document_copy_update_cannot_substitute_for_verified_registry() -> None:
    payload = decision_payload()
    for receipt in payload["support"]["coordinateReceipts"]:
        receipt["evidenceReceiptId"] = (
            f"support:miami-dade:miami:{receipt['workflow']}:{receipt['factFamily']}:{'f' * 64}"
        )
    document = IssuedSupportRegistryDocument.model_validate(issued_registry_payload())
    copied_receipts = tuple(
        issued.model_copy(
            update={
                "receipt_id": requested["evidenceReceiptId"],
                "source_id": "attacker-source",
                "evidence_sha256": "f" * 64,
                "issuer_id": "attacker",
                "key_version": "attacker-v1",
                "revoked_at": None,
            }
        )
        for issued, requested in zip(
            document.receipts,
            payload["support"]["coordinateReceipts"],
            strict=True,
        )
    )
    copied_document = document.model_copy(
        update={
            "receipts": copied_receipts,
            "_canonical_receipts": copied_receipts,
        }
    )

    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(json.dumps(payload)),
        receipt_registry=cast(VerifiedIssuedSupportRegistry, copied_document),
        evaluated_at=EVALUATED_AT,
    )
    assert result.status == "blocked"
    assert result.verified_ceiling_cents is None
    assert result.blocker_codes == ("support-registry-unverified",)


def test_input_alias_mutation_does_not_change_verified_registry() -> None:
    registry_payload = issued_registry_payload()
    registry = parse_issued_support_registry(json.dumps(registry_payload))
    registry_payload["receipts"].clear()

    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(json.dumps(decision_payload())),
        receipt_registry=registry,
        evaluated_at=EVALUATED_AT,
    )
    assert result.status == "released"


def test_registry_factory_credentials_are_not_module_exports() -> None:
    assert not hasattr(issued_support_registry, "_FACTORY_TOKEN")
    assert not hasattr(issued_support_registry, "_VerifiedIssuedSupportReceipt")
    assert not hasattr(issued_support_registry, "_build_verified_registry_boundary")
    with pytest.raises(TypeError):
        getattr(issued_support_registry, "VerifiedIssuedSupportRegistry")()


def test_unregistered_instance_of_verified_runtime_type_fails_closed() -> None:
    registry = parse_issued_support_registry(json.dumps(issued_registry_payload()))
    unregistered = object.__new__(type(registry))

    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(json.dumps(decision_payload())),
        receipt_registry=cast(VerifiedIssuedSupportRegistry, unregistered),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "blocked"
    assert result.recommendation == "abstain"
    assert result.verified_ceiling_cents is None
    assert result.blocker_codes == ("support-registry-unverified",)


def test_closure_membership_state_copy_cannot_authorize_a_forged_handle() -> None:
    registry = parse_issued_support_registry(json.dumps(issued_registry_payload()))
    forged = object.__new__(type(registry))
    weak_registries = [
        cell.cell_contents
        for cell in (getattr(parse_issued_support_registry, "__closure__", None) or ())
        if isinstance(cell.cell_contents, WeakKeyDictionary)
    ]
    if weak_registries:
        states = weak_registries[0]
        states[forged] = states[registry]

    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(json.dumps(decision_payload())),
        receipt_registry=cast(VerifiedIssuedSupportRegistry, forged),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "blocked"
    assert result.recommendation == "abstain"
    assert result.verified_ceiling_cents is None
    assert result.blocker_codes == ("support-registry-unverified",)


def test_content_relabel_with_copied_audit_digest_fails_closed() -> None:
    payload = decision_payload()
    forged_id = "opportunity-selected-forged-receipt"
    payload["support"]["coordinateReceipts"][0]["evidenceReceiptId"] = forged_id
    registry = parse_issued_support_registry(json.dumps(issued_registry_payload()))
    receipts = getattr(registry, "receipts")
    forged_receipts = (replace(receipts[0], receipt_id=forged_id), *receipts[1:])
    forged = object.__new__(type(registry))
    object.__setattr__(forged, "schema_version", getattr(registry, "schema_version"))
    object.__setattr__(forged, "registry_id", getattr(registry, "registry_id"))
    object.__setattr__(forged, "audit_sha256", getattr(registry, "audit_sha256"))
    object.__setattr__(forged, "receipts", forged_receipts)

    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(json.dumps(payload)),
        receipt_registry=cast(VerifiedIssuedSupportRegistry, forged),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "blocked"
    assert result.recommendation == "abstain"
    assert result.verified_ceiling_cents is None
    assert result.blocker_codes == ("support-registry-unverified",)


def test_opportunity_body_cannot_substitute_a_registry() -> None:
    payload = decision_payload()
    payload["issuedSupportRegistry"] = issued_registry_payload()

    with pytest.raises(ValidationError):
        parse_opportunity_decision_input(json.dumps(payload))
