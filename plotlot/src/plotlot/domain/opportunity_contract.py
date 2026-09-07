from __future__ import annotations

import hashlib
import json
from typing import NewType

from pydantic import Field

from plotlot.domain.opportunity_contract_models import (
    ExternalActionBoundaryProjection,
    OpportunityDecisionInput,
    OpportunityDecisionProjection,
    PersonaProjection,
    PrivateBetaPolicyProjection,
)
from plotlot.domain.opportunity_evaluator import (
    evaluate_opportunity_decision as evaluate_opportunity_decision,
)
from plotlot.domain.support_ledger import (
    ContractModel,
    MUNICIPALITY_LANES,
    WORKFLOW_FACT_FAMILIES,
    MunicipalityLaneDefinition,
    SupportLedgerEntry,
    WorkflowFactFamilies,
    build_initial_support_ledger,
)


ProjectionHash = NewType("ProjectionHash", str)


class ProductContractProjection(ContractModel):
    schema_version: str
    primary_buyer_persona: PersonaProjection
    decision_question: str
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]
    dimensions: dict[str, tuple[str, ...]]
    aggregate_states: tuple[str, ...]
    external_action_boundary: ExternalActionBoundaryProjection
    private_beta_policy: PrivateBetaPolicyProjection
    municipality_lanes: tuple[MunicipalityLaneDefinition, ...] = Field(min_length=9)
    workflow_fact_families: tuple[WorkflowFactFamilies, ...] = Field(min_length=4)
    initial_support_ledger: tuple[SupportLedgerEntry, ...] = Field(min_length=90)


def parse_opportunity_decision_input(raw: str) -> OpportunityDecisionInput:
    return OpportunityDecisionInput.model_validate_json(raw)


def parse_opportunity_decision_projection(raw: str) -> OpportunityDecisionProjection:
    return OpportunityDecisionProjection.model_validate_json(raw)


def product_contract_projection() -> ProductContractProjection:
    return ProductContractProjection(
        schema_version="PlotLotAcquisitionDecisionContractV1",
        primary_buyer_persona=PersonaProjection(
            buyer_kinds=(
                "general-contractor-developer",
                "private-investor",
                "land-developer",
            ),
            roles=("acquisition-lead", "preconstruction-lead"),
        ),
        decision_question="pursue-or-control-at-verified-ceiling",
        required_inputs=(
            "persona",
            "opportunity",
            "verified-property-identity",
            "verified-local-truth",
            "verified-constraints-capacity",
            "verified-market-evidence",
            "verified-underwriting",
            "municipality-support-receipts",
            "distinct-reviewer",
        ),
        required_outputs=(
            "recommendation",
            "verified-ceiling-cents",
            "readiness-dimensions",
            "blocker-codes",
            "evidence-receipts",
        ),
        dimensions={
            "processing": ("not-started", "running", "complete", "blocked"),
            "readiness": ("blocked", "provisional", "ready"),
            "pricing": ("unpriced", "provisional", "evidence-supported"),
            "review": ("unreviewed", "review-required", "approved"),
            "release": ("blocked", "eligible", "released"),
        },
        aggregate_states=("blocked", "provisional", "released"),
        external_action_boundary=ExternalActionBoundaryProjection(
            disabled=(
                "seller-contact",
                "lender-delivery",
                "offer-submission",
                "contract-language",
                "fund-movement",
            ),
            automatic=("signed-released-status-webhook",),
        ),
        private_beta_policy=PrivateBetaPolicyProjection(
            label="Miami-Dade private beta",
            initial_county="miami-dade",
            disabled_counties=("broward", "palm-beach"),
            county_boolean_implies_coverage=False,
        ),
        municipality_lanes=MUNICIPALITY_LANES,
        workflow_fact_families=WORKFLOW_FACT_FAMILIES,
        initial_support_ledger=build_initial_support_ledger(),
    )


def product_contract_projection_hash() -> ProjectionHash:
    projection = product_contract_projection().model_dump(mode="json", by_alias=True)
    canonical = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    return ProjectionHash(hashlib.sha256(canonical.encode()).hexdigest())
