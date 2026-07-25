from __future__ import annotations

from typing import Literal, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from plotlot.domain.support_ledger import (
    LANE_COUNTIES,
    ContractModel,
    County,
    MunicipalityLane,
)
from plotlot.domain.support_readiness_models import SupportReadinessInput


VerifiedFactStatus = Literal["verified", "ambiguous", "stale", "conflict"]
MarketEvidenceStatus = Literal["verified", "thin", "stale", "conflict"]


class BuyerPersonaInput(ContractModel):
    buyer_kind: Literal[
        "general-contractor-developer",
        "private-investor",
        "land-developer",
    ]
    role: Literal["acquisition-lead", "preconstruction-lead"]
    decision_intent: Literal["pursue", "control"]
    target_strategy: Literal[
        "build-to-sell",
        "build-to-rent",
        "renovate",
        "teardown",
        "subdivision",
        "hold",
    ]


class OpportunityInput(ContractModel):
    external_id: str = Field(min_length=1)
    address: str = Field(min_length=1)
    county: County
    municipality_lane: MunicipalityLane
    development_program_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def enforce_lane_county(self) -> OpportunityInput:
        if LANE_COUNTIES[self.municipality_lane] != self.county:
            raise PydanticCustomError(
                "lane_county_mismatch",
                "municipality lane does not belong to county",
            )
        return self


class VerifiedFactInput(ContractModel):
    status: VerifiedFactStatus
    evidence_receipt_ids: tuple[str, ...]

    @model_validator(mode="after")
    def verified_requires_receipts(self) -> VerifiedFactInput:
        if self.status == "verified" and not self.evidence_receipt_ids:
            raise PydanticCustomError(
                "verified_evidence_required",
                "verified facts require evidence receipts",
            )
        return self


class MarketEvidenceInput(ContractModel):
    status: MarketEvidenceStatus
    evidence_receipt_ids: tuple[str, ...]

    @model_validator(mode="after")
    def verified_requires_receipts(self) -> MarketEvidenceInput:
        if self.status == "verified" and not self.evidence_receipt_ids:
            raise PydanticCustomError(
                "verified_market_evidence_required",
                "verified market evidence requires receipts",
            )
        return self


class DecisionFactsInput(ContractModel):
    property_identity: VerifiedFactInput
    local_truth: VerifiedFactInput
    constraints_capacity: VerifiedFactInput
    market_evidence: MarketEvidenceInput
    underwriting: VerifiedFactInput


class ReviewInput(ContractModel):
    status: Literal["pending", "approved"]
    analyst_id: str = Field(min_length=1)
    reviewer_id: str | None = None

    @model_validator(mode="after")
    def approved_requires_distinct_reviewer(self) -> ReviewInput:
        if self.status == "approved" and (
            self.reviewer_id is None or self.reviewer_id == self.analyst_id
        ):
            raise PydanticCustomError(
                "distinct_reviewer_required",
                "approval requires a distinct reviewer",
            )
        return self


class OpportunityDecisionInput(ContractModel):
    schema_version: Literal["OpportunityDecisionInputV1"]
    persona: BuyerPersonaInput
    opportunity: OpportunityInput
    facts: DecisionFactsInput
    support: SupportReadinessInput
    proposed_ceiling_cents: int = Field(gt=0)
    review: ReviewInput
    requested_release: bool
    external_action: Literal["none"]

    @model_validator(mode="after")
    def enforce_support_opportunity_coordinate(self) -> OpportunityDecisionInput:
        if (
            self.support.county != self.opportunity.county
            or self.support.municipality_lane != self.opportunity.municipality_lane
        ):
            raise PydanticCustomError(
                "support_opportunity_mismatch",
                "support receipts must match the opportunity coordinate",
            )
        return self


class OpportunityDecisionProjection(ContractModel):
    schema_version: Literal["OpportunityDecisionProjectionV1"]
    processing: Literal["not-started", "running", "complete", "blocked"]
    readiness: Literal["blocked", "provisional", "ready"]
    pricing: Literal["unpriced", "provisional", "evidence-supported"]
    review: Literal["unreviewed", "review-required", "approved"]
    release: Literal["blocked", "eligible", "released"]
    status: Literal["blocked", "provisional", "released"]
    recommendation: Literal["abstain", "pursue", "control", "pass"]
    verified_ceiling_cents: int | None = Field(default=None, gt=0)
    evidence_receipt_ids: tuple[str, ...]
    blocker_codes: tuple[str, ...]

    @model_validator(mode="after")
    def prevent_status_widening(self) -> OpportunityDecisionProjection:
        match self.status:
            case "blocked":
                valid = (
                    self.processing == "blocked"
                    and self.readiness == "blocked"
                    and self.pricing == "unpriced"
                    and self.release == "blocked"
                    and self.recommendation == "abstain"
                    and self.verified_ceiling_cents is None
                    and bool(self.blocker_codes)
                )
            case "provisional":
                incomplete = (
                    self.processing == "complete"
                    and self.readiness == "provisional"
                    and self.pricing == "unpriced"
                    and self.release == "blocked"
                    and self.recommendation == "abstain"
                    and self.verified_ceiling_cents is None
                    and bool(self.blocker_codes)
                )
                eligible = (
                    self.processing == "complete"
                    and self.readiness == "ready"
                    and self.pricing == "evidence-supported"
                    and self.review == "approved"
                    and self.release == "eligible"
                    and self.recommendation in {"pursue", "control"}
                    and self.verified_ceiling_cents is not None
                    and bool(self.evidence_receipt_ids)
                    and not self.blocker_codes
                )
                valid = incomplete or eligible
            case "released":
                valid = (
                    self.processing == "complete"
                    and self.readiness == "ready"
                    and self.pricing == "evidence-supported"
                    and self.review == "approved"
                    and self.release == "released"
                    and self.recommendation in {"pursue", "control"}
                    and self.verified_ceiling_cents is not None
                    and bool(self.evidence_receipt_ids)
                    and not self.blocker_codes
                )
            case unreachable:
                assert_never(unreachable)
        if not valid:
            raise PydanticCustomError(
                "status_widening",
                "aggregate status exceeds its evidence dimensions",
            )
        return self


class PersonaProjection(ContractModel):
    buyer_kinds: tuple[str, ...]
    roles: tuple[str, ...]


class ExternalActionBoundaryProjection(ContractModel):
    disabled: tuple[str, ...]
    automatic: tuple[str, ...]


class PrivateBetaPolicyProjection(ContractModel):
    label: str
    initial_county: Literal["miami-dade"]
    disabled_counties: tuple[Literal["broward", "palm-beach"], ...]
    county_boolean_implies_coverage: Literal[False]
