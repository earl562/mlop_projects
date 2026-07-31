from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from plotlot.domain.support_ledger import (
    LANE_COUNTIES,
    WORKFLOW_FACT_FAMILIES,
    ContractModel,
    County,
    FactFamily,
    MunicipalityLane,
    Workflow,
)


class CoordinateReceiptInput(ContractModel):
    workflow: Workflow
    fact_family: FactFamily
    evidence_receipt_id: str = Field(min_length=1)


class SupportReadinessInput(ContractModel):
    county: County
    municipality_lane: MunicipalityLane
    coordinate_receipts: tuple[CoordinateReceiptInput, ...]

    @model_validator(mode="after")
    def enforce_exact_coordinate_receipts(self) -> SupportReadinessInput:
        if LANE_COUNTIES[self.municipality_lane] != self.county:
            raise PydanticCustomError(
                "lane_county_mismatch",
                "municipality lane does not belong to county",
            )
        coordinates = tuple(
            (receipt.workflow, receipt.fact_family) for receipt in self.coordinate_receipts
        )
        receipt_ids = tuple(receipt.evidence_receipt_id for receipt in self.coordinate_receipts)
        if len(set(coordinates)) != len(coordinates):
            raise PydanticCustomError(
                "duplicate_support_coordinate",
                "support coordinates must be unique",
            )
        if len(set(receipt_ids)) != len(receipt_ids):
            raise PydanticCustomError(
                "duplicate_evidence_receipt",
                "evidence receipt IDs must be unique",
            )
        allowed = {
            (definition.workflow, fact_family)
            for definition in WORKFLOW_FACT_FAMILIES
            for fact_family in definition.fact_families
        }
        if not set(coordinates).issubset(allowed):
            raise PydanticCustomError(
                "unsupported_coordinate",
                "support receipt coordinate is not in the contract",
            )
        return self
