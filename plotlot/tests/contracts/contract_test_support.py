from __future__ import annotations

import json
from pathlib import Path

type JsonValue = str | int | bool | None | list[JsonValue] | dict[str, JsonValue]

WORKFLOW_FACTS = {
    "opportunity-intake": ("property-identity", "jurisdiction"),
    "constraints-and-capacity": ("zoning", "development-constraints", "legal-capacity"),
    "market-underwriting": ("land-comps", "finished-resale-comps", "underwriting"),
    "decision-release": ("pricing-readiness", "reviewer-approval"),
}

REGISTRY_PATH = Path(__file__).parent / "goldens" / "issued-support-registry.json"


def issued_registry_payload() -> dict[str, JsonValue]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def issued_receipt_id(workflow: str, fact: str) -> str:
    return f"issued:plotlot-public-test-authority:public-test-v1:miami:{workflow}:{fact}"


def support_payload(
    county: str = "miami-dade",
    lane: str = "miami",
    *,
    complete: bool = True,
) -> dict[str, JsonValue]:
    receipts = [
        {
            "workflow": workflow,
            "factFamily": fact,
            "evidenceReceiptId": (
                issued_receipt_id(workflow, fact)
                if (county, lane) == ("miami-dade", "miami")
                else f"unissued:{county}:{lane}:{workflow}:{fact}"
            ),
        }
        for workflow, facts in WORKFLOW_FACTS.items()
        for fact in facts
    ]
    return {
        "county": county,
        "municipalityLane": lane,
        "coordinateReceipts": receipts if complete else [],
    }


def decision_payload(
    *,
    identity: str = "verified",
    local_truth: str = "verified",
    capacity: str = "verified",
    market: str = "verified",
    underwriting: str = "verified",
    support: str = "supported",
    requested_release: bool = True,
) -> dict[str, JsonValue]:
    return {
        "schemaVersion": "OpportunityDecisionInputV1",
        "persona": {
            "buyerKind": "general-contractor-developer",
            "role": "acquisition-lead",
            "decisionIntent": "control",
            "targetStrategy": "build-to-sell",
        },
        "opportunity": {
            "externalId": "golden-001",
            "address": "100 Test Ave, Miami, FL 33101",
            "county": "miami-dade",
            "municipalityLane": "miami",
            "developmentProgramId": "program-001",
        },
        "facts": {
            "propertyIdentity": {"status": identity, "evidenceReceiptIds": ["receipt-identity"]},
            "localTruth": {"status": local_truth, "evidenceReceiptIds": ["receipt-truth"]},
            "constraintsCapacity": {
                "status": capacity,
                "evidenceReceiptIds": ["receipt-capacity"],
            },
            "marketEvidence": {"status": market, "evidenceReceiptIds": ["receipt-market"]},
            "underwriting": {
                "status": underwriting,
                "evidenceReceiptIds": ["receipt-underwriting"],
            },
        },
        "support": support_payload(complete=support == "supported"),
        "proposedCeilingCents": 52_500_000,
        "review": {
            "status": "approved",
            "analystId": "analyst-001",
            "reviewerId": "reviewer-002",
        },
        "requestedRelease": requested_release,
        "externalAction": "none",
    }
