from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
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

ReceiptFailure = Literal[
    "unissued",
    "rebound",
    "revoked",
    "expired",
    "not-yet-issued",
    "registry-unverified",
]


class IssuedSupportReceiptDocument(ContractModel):
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
    def validate_issuance(self) -> IssuedSupportReceiptDocument:
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


class IssuedSupportRegistryDocument(ContractModel):
    schema_version: Literal["IssuedSupportRegistryV1"]
    receipts: tuple[IssuedSupportReceiptDocument, ...]

    @model_validator(mode="after")
    def reject_duplicates(self) -> IssuedSupportRegistryDocument:
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


@dataclass(frozen=True, slots=True)
class _VerifiedIssuedSupportReceipt:
    receipt_id: str
    county: County
    municipality_lane: MunicipalityLane
    workflow: Workflow
    fact_family: FactFamily
    source_id: str
    evidence_sha256: str
    issuer_id: str
    key_version: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


_FACTORY_TOKEN = object()


class VerifiedIssuedSupportRegistry:
    __slots__ = ("__receipts_by_id",)
    __receipts_by_id: MappingProxyType[str, _VerifiedIssuedSupportReceipt]

    def __init__(
        self,
        factory_token: object,
        receipts: tuple[_VerifiedIssuedSupportReceipt, ...],
    ) -> None:
        if factory_token is not _FACTORY_TOKEN:
            raise TypeError("verified registries can only be created by the parser")
        object.__setattr__(
            self,
            "_VerifiedIssuedSupportRegistry__receipts_by_id",
            MappingProxyType({receipt.receipt_id: receipt for receipt in receipts}),
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("verified registry is immutable")

    def __copy__(self) -> VerifiedIssuedSupportRegistry:
        raise TypeError("verified registry cannot be copied")

    def __deepcopy__(self, memo: object) -> VerifiedIssuedSupportRegistry:
        raise TypeError("verified registry cannot be copied")

    def __reduce__(self) -> str | tuple[object, ...]:
        raise TypeError("verified registry cannot be serialized")

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
        issued = self.__receipts_by_id.get(receipt_id)
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


def parse_issued_support_registry(raw: str) -> VerifiedIssuedSupportRegistry:
    document = cast(
        IssuedSupportRegistryDocument,
        IssuedSupportRegistryDocument.model_validate_json(raw),
    )
    receipts = tuple(
        _VerifiedIssuedSupportReceipt(
            receipt_id=receipt.receipt_id,
            county=receipt.county,
            municipality_lane=receipt.municipality_lane,
            workflow=receipt.workflow,
            fact_family=receipt.fact_family,
            source_id=receipt.source_id,
            evidence_sha256=receipt.evidence_sha256,
            issuer_id=receipt.issuer_id,
            key_version=receipt.key_version,
            issued_at=receipt.issued_at,
            expires_at=receipt.expires_at,
            revoked_at=receipt.revoked_at,
        )
        for receipt in document.receipts
    )
    return VerifiedIssuedSupportRegistry(_FACTORY_TOKEN, receipts)
