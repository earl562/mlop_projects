from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from collections.abc import Callable
from typing import Literal, Protocol, TypeGuard, cast
from weakref import WeakKeyDictionary

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


class VerifiedIssuedSupportRegistry(Protocol):
    pass


def _build_verified_registry_boundary() -> tuple[
    Callable[[str], VerifiedIssuedSupportRegistry],
    Callable[[object], TypeGuard[VerifiedIssuedSupportRegistry]],
    Callable[..., ReceiptFailure | None],
]:
    @dataclass(frozen=True, slots=True)
    class VerifiedReceipt:
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

    class Registry:
        __slots__ = ("__weakref__",)

        def __setattr__(self, name: str, value: object) -> None:
            raise AttributeError("verified registry is immutable")

        def __copy__(self) -> Registry:
            raise TypeError("verified registry cannot be copied")

        def __deepcopy__(self, memo: object) -> Registry:
            raise TypeError("verified registry cannot be copied")

        def __reduce__(self) -> str | tuple[object, ...]:
            raise TypeError("verified registry cannot be serialized")

    states: WeakKeyDictionary[Registry, MappingProxyType[str, VerifiedReceipt]] = (
        WeakKeyDictionary()
    )

    def parse(raw: str) -> VerifiedIssuedSupportRegistry:
        document = cast(
            IssuedSupportRegistryDocument,
            IssuedSupportRegistryDocument.model_validate_json(raw),
        )
        receipts = tuple(
            VerifiedReceipt(
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
        registry = Registry()
        states[registry] = MappingProxyType({receipt.receipt_id: receipt for receipt in receipts})
        return cast(VerifiedIssuedSupportRegistry, registry)

    def is_verified(value: object) -> TypeGuard[VerifiedIssuedSupportRegistry]:
        if type(value) is not Registry:
            return False
        return cast(Registry, value) in states

    def verify(
        registry: object,
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
        if not is_verified(registry):
            return "registry-unverified"
        issued = states[cast(Registry, registry)].get(receipt_id)
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

    return parse, is_verified, verify


(
    parse_issued_support_registry,
    is_verified_issued_support_registry,
    verify_issued_support_receipt,
) = _build_verified_registry_boundary()
del _build_verified_registry_boundary
