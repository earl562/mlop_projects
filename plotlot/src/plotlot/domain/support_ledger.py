from __future__ import annotations

from typing import Literal, cast

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from plotlot.domain.support_coordinate import (
    LANE_COUNTIES,
    ContractModel,
    County,
    FactFamily,
    MunicipalityLane,
    Workflow,
)


class MunicipalityLaneDefinition(ContractModel):
    county: County
    municipality_lane: MunicipalityLane
    label: str = Field(min_length=1)


class WorkflowFactFamilies(ContractModel):
    workflow: Workflow
    fact_families: tuple[FactFamily, ...] = Field(min_length=1)


class SupportLedgerEntry(ContractModel):
    schema_version: Literal["MunicipalitySupportLedgerEntryV1"] = "MunicipalitySupportLedgerEntryV1"
    county: County
    municipality_lane: MunicipalityLane
    workflow: Workflow
    fact_family: FactFamily
    status: Literal["unsupported", "supported"]
    evidence_receipt_ids: tuple[str, ...]

    @model_validator(mode="after")
    def enforce_evidence_bound_status(self) -> SupportLedgerEntry:
        if LANE_COUNTIES[self.municipality_lane] != self.county:
            raise PydanticCustomError(
                "lane_county_mismatch",
                "municipality lane does not belong to county",
            )
        receipt_count = len(self.evidence_receipt_ids)
        if self.status == "supported" and receipt_count == 0:
            raise PydanticCustomError(
                "support_evidence_required",
                "supported entries require evidence receipts",
            )
        if self.status == "unsupported" and receipt_count != 0:
            raise PydanticCustomError(
                "unsupported_receipts_forbidden",
                "unsupported entries cannot carry promotion receipts",
            )
        if len(set(self.evidence_receipt_ids)) != receipt_count:
            raise PydanticCustomError(
                "duplicate_evidence_receipt",
                "duplicate evidence receipt IDs are forbidden",
            )
        return self


class SupportPromotionRequest(ContractModel):
    schema_version: Literal["SupportPromotionRequestV1"]
    county: County
    municipality_lane: MunicipalityLane
    workflow: Workflow
    fact_family: FactFamily
    evidence_receipt_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def enforce_workflow_fact_family(self) -> SupportPromotionRequest:
        if LANE_COUNTIES[self.municipality_lane] != self.county:
            raise PydanticCustomError(
                "lane_county_mismatch",
                "municipality lane does not belong to county",
            )
        allowed = next(
            definition.fact_families
            for definition in WORKFLOW_FACT_FAMILIES
            if definition.workflow == self.workflow
        )
        if self.fact_family not in allowed:
            raise PydanticCustomError(
                "workflow_fact_family_mismatch",
                "fact family does not belong to workflow",
            )
        if len(set(self.evidence_receipt_ids)) != len(self.evidence_receipt_ids):
            raise PydanticCustomError(
                "duplicate_evidence_receipt",
                "duplicate evidence receipt IDs are forbidden",
            )
        return self


MUNICIPALITY_LANES = (
    MunicipalityLaneDefinition(
        county="miami-dade",
        municipality_lane="miami",
        label="Miami",
    ),
    MunicipalityLaneDefinition(
        county="miami-dade",
        municipality_lane="miami-gardens",
        label="Miami Gardens",
    ),
    MunicipalityLaneDefinition(
        county="miami-dade",
        municipality_lane="unincorporated-miami-dade",
        label="Unincorporated Miami-Dade",
    ),
    MunicipalityLaneDefinition(
        county="broward",
        municipality_lane="fort-lauderdale",
        label="Fort Lauderdale",
    ),
    MunicipalityLaneDefinition(
        county="broward",
        municipality_lane="miramar",
        label="Miramar",
    ),
    MunicipalityLaneDefinition(
        county="broward",
        municipality_lane="hollywood",
        label="Hollywood",
    ),
    MunicipalityLaneDefinition(
        county="palm-beach",
        municipality_lane="west-palm-beach",
        label="West Palm Beach",
    ),
    MunicipalityLaneDefinition(
        county="palm-beach",
        municipality_lane="boca-raton",
        label="Boca Raton",
    ),
    MunicipalityLaneDefinition(
        county="palm-beach",
        municipality_lane="unincorporated-palm-beach-loxahatchee",
        label="Unincorporated Palm Beach/Loxahatchee",
    ),
)

WORKFLOW_FACT_FAMILIES = (
    WorkflowFactFamilies(
        workflow="opportunity-intake",
        fact_families=("property-identity", "jurisdiction"),
    ),
    WorkflowFactFamilies(
        workflow="constraints-and-capacity",
        fact_families=("zoning", "development-constraints", "legal-capacity"),
    ),
    WorkflowFactFamilies(
        workflow="market-underwriting",
        fact_families=(
            "land-comps",
            "finished-resale-comps",
            "underwriting",
        ),
    ),
    WorkflowFactFamilies(
        workflow="decision-release",
        fact_families=("pricing-readiness", "reviewer-approval"),
    ),
)


def build_initial_support_ledger() -> tuple[SupportLedgerEntry, ...]:
    return tuple(
        SupportLedgerEntry(
            county=lane.county,
            municipality_lane=lane.municipality_lane,
            workflow=definition.workflow,
            fact_family=fact_family,
            status="unsupported",
            evidence_receipt_ids=(),
        )
        for lane in MUNICIPALITY_LANES
        for definition in WORKFLOW_FACT_FAMILIES
        for fact_family in definition.fact_families
    )


def parse_support_promotion_request(raw: str) -> SupportPromotionRequest:
    return cast(
        SupportPromotionRequest,
        SupportPromotionRequest.model_validate_json(raw),
    )
