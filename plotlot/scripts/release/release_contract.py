from __future__ import annotations

from datetime import timedelta
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Frontend(ContractModel):
    provider: Literal["vercel"]
    plan: str
    deployment_id: str
    public_https: bool


class ServiceAssertion(ContractModel):
    version: Literal["1.0"]
    algorithm: Literal["Ed25519"]
    audience: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    key_owner: str = Field(min_length=1)
    kid: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def assertion_lifetime_is_bounded(self) -> Self:
        lifetime = self.expires_at - self.issued_at
        if lifetime <= timedelta(0):
            raise PydanticCustomError(
                "service_assertion_deadline",
                "expires_at must follow issued_at",
            )
        if lifetime > timedelta(minutes=5):
            raise PydanticCustomError(
                "service_assertion_lifetime",
                "service assertion lifetime cannot exceed five minutes",
            )
        return self


class Service(ContractModel):
    name: str
    provider: Literal["render"]
    plan: str
    exposure: Literal["public", "private"]
    tls: Literal["required", "disabled"]
    image_digest: str
    service_assertion: ServiceAssertion


class Deployment(ContractModel):
    frontend: Frontend
    services: tuple[Service, ...]


class DatabaseSchema(ContractModel):
    name: str
    role: str


class Backup(ContractModel):
    enabled: bool
    pitr: bool
    restore_owner: str
    rpo_minutes: int
    rto_hours: int


class Database(ContractModel):
    provider: Literal["neon"]
    network_access: Literal["private", "public"]
    tls: Literal["verify-full", "disabled"]
    schemas: tuple[DatabaseSchema, ...]
    backup: Backup


class ObjectStore(ContractModel):
    compatibility: Literal["s3"]
    access: Literal["private", "public"]
    tls: Literal["required", "disabled"]
    immutability: Literal["object-lock"]
    encryption: str
    key_owner: str | None = None


class Secret(ContractModel):
    name: str
    owner: str | None = None
    rotation_days: int


class DataPolicy(ContractModel):
    classification: str
    rights_basis: str
    retention_days: int | None = None
    deletion_owner: str


class Entitlements(ContractModel):
    mode: Literal["manual"]
    owner: str


class DedicatedDeployments(ContractModel):
    code_fork: bool
    digest_parity: bool
    schema_parity: bool
    setup: Literal["paid"]


class Incident(ContractModel):
    owner: str
    rollback_owner: str
    rollback_manifest: str


class Slo(ContractModel):
    name: str
    target: str
    owner: str


class Governance(ContractModel):
    data_policies: tuple[DataPolicy, ...]
    entitlements: Entitlements
    dedicated_deployments: DedicatedDeployments
    incident: Incident
    slos: tuple[Slo, ...]


class Contracts(ContractModel):
    plotlot_openapi_sha256: str
    byright_expected_openapi_sha256: str
    migration_head: str
    database_schema_sha256: str


class Signature(ContractModel):
    algorithm: Literal["Ed25519"]
    key_id: str
    signed_by: str
    payload_sha256: str
    value: str


class ReleaseCandidate(ContractModel):
    schema_version: Literal["1.0"]
    environment: Literal["production"]
    deployment: Deployment
    database: Database
    object_store: ObjectStore
    secrets: tuple[Secret, ...]
    governance: Governance
    contracts: Contracts
    signature: Signature | None = None


class ReleaseManifest(ReleaseCandidate):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={"$id": "https://plotlot.app/schemas/release-manifest-v1.json"},
    )

    signature: Signature
