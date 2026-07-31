from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from plotlot.domain.support_promotion import apply_support_promotion
from plotlot.domain.issued_support_registry import parse_issued_support_registry
from plotlot.domain.support_ledger import (
    SupportLedgerEntry,
    build_initial_support_ledger,
    parse_support_promotion_request,
)
from tests.contracts.contract_test_support import (
    issued_receipt_id,
    issued_registry_payload,
)

RECEIPT = issued_receipt_id("opportunity-intake", "property-identity")
REGISTRY = parse_issued_support_registry(json.dumps(issued_registry_payload()))
EVALUATED_AT = datetime(2026, 7, 25, tzinfo=UTC)


def promote(ledger, request):
    return apply_support_promotion(
        ledger,
        request,
        receipt_registry=REGISTRY,
        evaluated_at=EVALUATED_AT,
    )


def test_initial_ledger_lists_every_lane_workflow_fact_family_as_unsupported() -> None:
    ledger = build_initial_support_ledger()
    coordinates = {(entry.municipality_lane, entry.workflow, entry.fact_family) for entry in ledger}

    assert len(ledger) == 90
    assert len(coordinates) == 90
    assert {entry.municipality_lane for entry in ledger} == {
        "miami",
        "miami-gardens",
        "unincorporated-miami-dade",
        "fort-lauderdale",
        "miramar",
        "hollywood",
        "west-palm-beach",
        "boca-raton",
        "unincorporated-palm-beach-loxahatchee",
    }
    assert all(entry.status == "unsupported" for entry in ledger)
    assert all(entry.evidence_receipt_ids == () for entry in ledger)


def test_rejects_county_level_promotion_boolean() -> None:
    request = {
        "schemaVersion": "SupportPromotionRequestV1",
        "county": "miami-dade",
        "municipalityLane": "miami",
        "workflow": "opportunity-intake",
        "factFamily": "property-identity",
        "evidenceReceiptIds": [RECEIPT],
        "countyEnabled": True,
    }

    with pytest.raises(ValidationError):
        parse_support_promotion_request(json.dumps(request))


def test_promotes_only_one_coordinate_with_evidence_receipt() -> None:
    ledger = build_initial_support_ledger()
    request = parse_support_promotion_request(
        json.dumps(
            {
                "schemaVersion": "SupportPromotionRequestV1",
                "county": "miami-dade",
                "municipalityLane": "miami",
                "workflow": "opportunity-intake",
                "factFamily": "property-identity",
                "evidenceReceiptIds": [RECEIPT],
            }
        )
    )

    promoted = promote(ledger, request)

    assert sum(entry.status == "supported" for entry in promoted) == 1
    selected = next(entry for entry in promoted if entry.status == "supported")
    assert selected.municipality_lane == "miami"
    assert selected.evidence_receipt_ids == (RECEIPT,)


def test_rejects_promotion_without_evidence_receipt() -> None:
    request = {
        "schemaVersion": "SupportPromotionRequestV1",
        "county": "miami-dade",
        "municipalityLane": "miami",
        "workflow": "opportunity-intake",
        "factFamily": "property-identity",
        "evidenceReceiptIds": [],
    }

    with pytest.raises(ValidationError):
        parse_support_promotion_request(json.dumps(request))


def test_rejects_disabled_county_and_lane_county_mismatch() -> None:
    broward = {
        "schemaVersion": "SupportPromotionRequestV1",
        "county": "broward",
        "municipalityLane": "fort-lauderdale",
        "workflow": "opportunity-intake",
        "factFamily": "property-identity",
        "evidenceReceiptIds": [
            f"support:broward:fort-lauderdale:opportunity-intake:property-identity:{'b' * 64}"
        ],
    }
    with pytest.raises(ValueError, match="county is not enabled"):
        promote(
            build_initial_support_ledger(),
            parse_support_promotion_request(json.dumps(broward)),
        )

    broward["municipalityLane"] = "miami"
    with pytest.raises(ValidationError):
        parse_support_promotion_request(json.dumps(broward))


def test_rejects_duplicate_coordinates_receipts_and_conflicting_repromotion() -> None:
    ledger = build_initial_support_ledger()
    request = parse_support_promotion_request(
        json.dumps(
            {
                "schemaVersion": "SupportPromotionRequestV1",
                "county": "miami-dade",
                "municipalityLane": "miami",
                "workflow": "opportunity-intake",
                "factFamily": "property-identity",
                "evidenceReceiptIds": [RECEIPT],
            }
        )
    )
    duplicate_ledger = ledger + (ledger[0],)
    with pytest.raises(ValueError, match="duplicate support coordinate"):
        promote(duplicate_ledger, request)

    duplicate_receipts = request.model_copy(update={"evidence_receipt_ids": (RECEIPT, RECEIPT)})
    with pytest.raises(ValueError, match="duplicate evidence receipt"):
        promote(ledger, duplicate_receipts)

    promoted = promote(ledger, request)
    assert promote(promoted, request) == promoted
    conflicting = request.model_copy(
        update={"evidence_receipt_ids": ("unissued-conflicting-receipt",)}
    )
    with pytest.raises(ValueError, match="support receipt is unissued"):
        promote(promoted, conflicting)


def test_rejects_ledger_entry_lane_county_mismatch() -> None:
    with pytest.raises(ValidationError):
        SupportLedgerEntry(
            county="broward",
            municipality_lane="miami",
            workflow="opportunity-intake",
            fact_family="property-identity",
            status="unsupported",
            evidence_receipt_ids=(),
        )
