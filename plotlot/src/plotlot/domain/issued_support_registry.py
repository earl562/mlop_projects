from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import Field, PrivateAttr, model_validator
from pydantic_core import PydanticCustomError

from plotlot.domain.support_coordinate import (
    LANE_COUNTIES,
    ContractModel,
    County,
    FactFamily,
    MunicipalityLane,
    Workflow,
)

ReceiptFailure = Literal["unissued", "rebound", "revoked", "expired", "not-yet-issued"]


class IssuedSupportReceipt(ContractModel):
    schema_version: Literal["IssuedSupportReceiptV1"]
    receipt_id: str = Field(min_length=1)
    county: County
    municipality_lane: MunicipalityLane
    workflow: Workflow
    fact_family: FactFamily
    source_id: str = Field(min_length=1)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issuer_id: Literal["plotlot-public-test-authority"]
    key_version: Literal["public-test-v1"]
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None

    @model_validator(mode="after")
    def validate_issuance(self) -> IssuedSupportReceipt:
        if LANE_COUNTIES[self.municipality_lane] != self.county:
            raise PydanticCustomError(
                "lane_county_mismatch", "receipt lane does not belong to county"
            )
        timestamps = (self.issued_at, self.expires_at, self.revoked_at)
        if any(value is not None and value.utcoffset() is None for value in timestamps):
            raise PydanticCustomError(
                "timezone_required", "issuance timestamps require UTC offsets"
            )
        if self.issued_at >= self.expires_at:
            raise PydanticCustomError("invalid_issuance_window", "issuedAt must precede expiresAt")
        return self


class IssuedSupportRegistry(ContractModel):
    schema_version: Literal["IssuedSupportRegistryV1"]
    receipts: tuple[IssuedSupportReceipt, ...]
    _canonical_receipts: tuple[IssuedSupportReceipt, ...] = PrivateAttr(default=())

    def model_post_init(self, context: object, /) -> None:
        self._canonical_receipts = self.receipts

    @model_validator(mode="after")
    def reject_duplicates(self) -> IssuedSupportRegistry:
        receipt_ids = [receipt.receipt_id for receipt in self.receipts]
        coordinates = [
            (
                receipt.county,
                receipt.municipality_lane,
                receipt.workflow,
                receipt.fact_family,
            )
            for receipt in self.receipts
        ]
        if len(set(receipt_ids)) != len(receipt_ids):
            raise PydanticCustomError(
                "duplicate_issued_receipt", "issued receipt IDs must be unique"
            )
        if len(set(coordinates)) != len(coordinates):
            raise PydanticCustomError(
                "duplicate_issued_coordinate", "issued receipt coordinates must be unique"
            )
        return self

    def verify(
        self,
        *,
        receipt_id: str,
        county: County,
        municipality_lane: MunicipalityLane,
        workflow: Workflow,
        fact_family: FactFamily,
        evaluated_at: datetime,
    ) -> ReceiptFailure | None:
        if evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at requires a UTC offset")
        issued = next(
            (receipt for receipt in self._canonical_receipts if receipt.receipt_id == receipt_id),
            None,
        )
        if issued is None:
            return "unissued"
        if (
            issued.county,
            issued.municipality_lane,
            issued.workflow,
            issued.fact_family,
        ) != (county, municipality_lane, workflow, fact_family):
            return "rebound"
        if issued.revoked_at is not None and issued.revoked_at <= evaluated_at:
            return "revoked"
        if issued.expires_at <= evaluated_at:
            return "expired"
        if issued.issued_at > evaluated_at:
            return "not-yet-issued"
        return None


def parse_issued_support_registry(raw: str) -> IssuedSupportRegistry:
    return cast(
        IssuedSupportRegistry,
        IssuedSupportRegistry.model_validate_json(raw),
    )
