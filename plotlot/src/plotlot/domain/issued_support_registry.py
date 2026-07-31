from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, TypeGuard, cast

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

RegistryId = Literal[
    "plotlot-public-test-registry-2026-07-25",
    "plotlot-public-test-registry-revoked-2026-07-24",
]

SUPPORTED_REGISTRY_DIGESTS: dict[RegistryId, str] = {
    "plotlot-public-test-registry-2026-07-25": (
        "5e694f5ae479bd2036f23d9dcb4bb233f60da3cfc3662985bb7697b0b2fb0e1c"
    ),
    "plotlot-public-test-registry-revoked-2026-07-24": (
        "251c8b36f80a7d2ca792868900a75c8589334914a4257f36c69a392f1f271098"
    ),
}


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


@dataclass(frozen=True, slots=True)
class _VerifiedReceipt:
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


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _receipt_payload(
    receipt: IssuedSupportReceiptDocument | _VerifiedReceipt,
) -> dict[str, str | None]:
    return {
        "schemaVersion": "IssuedSupportReceiptV1",
        "receiptId": receipt.receipt_id,
        "county": receipt.county,
        "municipalityLane": receipt.municipality_lane,
        "workflow": receipt.workflow,
        "factFamily": receipt.fact_family,
        "sourceId": receipt.source_id,
        "evidenceSha256": receipt.evidence_sha256,
        "issuerId": receipt.issuer_id,
        "keyVersion": receipt.key_version,
        "issuedAt": _timestamp(receipt.issued_at),
        "expiresAt": _timestamp(receipt.expires_at),
        "revokedAt": _timestamp(receipt.revoked_at),
    }


def _registry_digest(
    schema_version: str,
    registry_id: RegistryId,
    receipts: tuple[IssuedSupportReceiptDocument, ...] | tuple[_VerifiedReceipt, ...],
) -> str:
    payload = {
        "schemaVersion": schema_version,
        "registryId": registry_id,
        "receipts": [_receipt_payload(receipt) for receipt in receipts],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class IssuedSupportRegistryDocument(ContractModel):
    schema_version: Literal["IssuedSupportRegistryV2"]
    registry_id: RegistryId
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
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
        expected = SUPPORTED_REGISTRY_DIGESTS[self.registry_id]
        actual = _registry_digest(self.schema_version, self.registry_id, self.receipts)
        if self.audit_sha256 != expected or actual != expected:
            raise PydanticCustomError(
                "registry_authenticity_mismatch",
                "registry content does not match its pinned audit digest",
            )
        return self


class VerifiedIssuedSupportRegistry(Protocol):
    pass


class _VerifiedRegistry:
    __slots__ = ("audit_sha256", "receipts", "registry_id", "schema_version")
    schema_version: Literal["IssuedSupportRegistryV2"]
    registry_id: RegistryId
    audit_sha256: str
    receipts: tuple[_VerifiedReceipt, ...]

    def __init__(
        self,
        *,
        schema_version: Literal["IssuedSupportRegistryV2"],
        registry_id: RegistryId,
        audit_sha256: str,
        receipts: tuple[_VerifiedReceipt, ...],
    ) -> None:
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "registry_id", registry_id)
        object.__setattr__(self, "audit_sha256", audit_sha256)
        object.__setattr__(self, "receipts", receipts)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("verified registry is immutable")

    def __copy__(self) -> _VerifiedRegistry:
        raise TypeError("verified registry cannot be copied")

    def __deepcopy__(self, memo: object) -> _VerifiedRegistry:
        raise TypeError("verified registry cannot be copied")

    def __reduce__(self) -> str | tuple[object, ...]:
        raise TypeError("verified registry cannot be serialized")


def _has_authentic_content(registry: _VerifiedRegistry) -> bool:
    expected = SUPPORTED_REGISTRY_DIGESTS.get(registry.registry_id)
    if expected is None or registry.audit_sha256 != expected:
        return False
    return (
        _registry_digest(registry.schema_version, registry.registry_id, registry.receipts)
        == expected
    )


def parse_issued_support_registry(raw: str) -> VerifiedIssuedSupportRegistry:
    document = cast(
        IssuedSupportRegistryDocument,
        IssuedSupportRegistryDocument.model_validate_json(raw),
    )
    receipts = tuple(
        _VerifiedReceipt(
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
    return cast(
        VerifiedIssuedSupportRegistry,
        _VerifiedRegistry(
            schema_version=document.schema_version,
            registry_id=document.registry_id,
            audit_sha256=document.audit_sha256,
            receipts=receipts,
        ),
    )


def is_verified_issued_support_registry(
    value: object,
) -> TypeGuard[VerifiedIssuedSupportRegistry]:
    if type(value) is not _VerifiedRegistry:
        return False
    try:
        return _has_authentic_content(cast(_VerifiedRegistry, value))
    except (AttributeError, TypeError):
        return False


def verify_issued_support_receipt(
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
    if not is_verified_issued_support_registry(registry):
        return "registry-unverified"
    verified = cast(_VerifiedRegistry, registry)
    issued = next(
        (receipt for receipt in verified.receipts if receipt.receipt_id == receipt_id),
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
