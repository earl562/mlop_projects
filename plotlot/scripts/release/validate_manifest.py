#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pydantic>=2.0"]
# ///
# ─── How to run ───
# uv run python scripts/release/validate_manifest.py tests/fixtures/release/valid.json

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Frontend(ContractModel):
    provider: Literal["vercel"]
    plan: str
    deployment_id: str
    public_https: bool


class ServiceAssertion(ContractModel):
    algorithm: Literal["Ed25519"]
    audience: str
    issuer: str
    key_owner: str | None = None


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


Policy = tuple[str, Callable[[ReleaseCandidate], bool]]


def policy_results(manifest: ReleaseCandidate) -> list[str]:
    policies: tuple[Policy, ...] = (
        (
            "PROD_FREE_PLAN",
            lambda item: (
                item.deployment.frontend.plan != "free"
                and all(service.plan != "free" for service in item.deployment.services)
            ),
        ),
        ("DATABASE_PUBLIC", lambda item: item.database.network_access == "private"),
        (
            "TLS_REQUIRED",
            lambda item: (
                item.deployment.frontend.public_https
                and item.database.tls == "verify-full"
                and item.object_store.tls == "required"
                and all(service.tls == "required" for service in item.deployment.services)
            ),
        ),
        (
            "SECRET_OWNER_REQUIRED",
            lambda item: (
                bool(item.object_store.key_owner)
                and all(secret.owner for secret in item.secrets)
                and all(service.service_assertion.key_owner for service in item.deployment.services)
            ),
        ),
        (
            "DATABASE_ROLE_ISOLATION",
            lambda item: (
                len({schema.role for schema in item.database.schemas}) == len(item.database.schemas)
            ),
        ),
        (
            "BACKUP_PITR_REQUIRED",
            lambda item: (
                item.database.backup.enabled
                and item.database.backup.pitr
                and bool(item.database.backup.restore_owner)
            ),
        ),
        (
            "RPO_BREACH",
            lambda item: item.database.backup.rpo_minutes <= 15,
        ),
        (
            "RTO_BREACH",
            lambda item: item.database.backup.rto_hours <= 4,
        ),
        (
            "RETENTION_POLICY_REQUIRED",
            lambda item: all(
                policy.retention_days is not None and policy.retention_days > 0
                for policy in item.governance.data_policies
            ),
        ),
        (
            "CONTRACT_HASH_MISMATCH",
            lambda item: (
                item.contracts.plotlot_openapi_sha256
                == item.contracts.byright_expected_openapi_sha256
            ),
        ),
        (
            "CUSTOMER_CODE_FORK_FORBIDDEN",
            lambda item: not item.governance.dedicated_deployments.code_fork,
        ),
        (
            "RELEASE_SIGNATURE_REQUIRED",
            lambda item: (
                item.signature is not None
                and bool(item.signature.key_id)
                and bool(item.signature.signed_by)
                and bool(item.signature.payload_sha256)
                and bool(item.signature.value)
            ),
        ),
        (
            "DEDICATED_PARITY_REQUIRED",
            lambda item: (
                item.governance.dedicated_deployments.digest_parity
                and item.governance.dedicated_deployments.schema_parity
            ),
        ),
    )
    return [code for code, passes in policies if not passes(manifest)]


def report(path: Path, codes: list[str]) -> str:
    return json.dumps(
        {
            "codes": codes,
            "manifest": os.path.relpath(path, Path.cwd()),
            "valid": not codes,
        },
        sort_keys=True,
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(json.dumps({"codes": ["USAGE_ERROR"], "valid": False}, sort_keys=True))
        return 2

    path = Path(argv[1])
    try:
        manifest = ReleaseCandidate.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        print(
            json.dumps(
                {
                    "codes": ["MANIFEST_SCHEMA_INVALID"],
                    "detail": str(error),
                    "manifest": os.path.relpath(path, Path.cwd()),
                    "valid": False,
                },
                sort_keys=True,
            )
        )
        return 2

    codes = policy_results(manifest)
    print(report(path, codes))
    return 1 if codes else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
