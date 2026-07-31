from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import TypedDict

from pydantic import TypeAdapter

from scripts.release.release_contract import ReleaseManifest


ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "artifacts" / "release" / "manifests" / "production-architecture.json"
SCHEMA = ROOT / "artifacts" / "release" / "release-manifest.schema.json"


class SignatureSchema(TypedDict):
    required: list[str]


class SchemaDefinitions(TypedDict):
    ServiceAssertion: SignatureSchema
    Signature: SignatureSchema


ReleaseSchema = TypedDict(
    "ReleaseSchema",
    {"$id": str, "$defs": SchemaDefinitions, "required": list[str]},
)
SCHEMA_ADAPTER = TypeAdapter(ReleaseSchema)


def test_production_topology_uses_paid_private_canonical_services() -> None:
    manifest = ReleaseManifest.model_validate_json(ARCHITECTURE.read_text(encoding="utf-8"))

    assert manifest.deployment.frontend.provider == "vercel"
    assert manifest.deployment.frontend.plan == "pro"
    assert {
        (service.name, service.provider, service.exposure)
        for service in manifest.deployment.services
    } == {
        ("plotlot-api", "render", "public"),
        ("plotlot-worker", "render", "private"),
        ("byright-api", "render", "private"),
        ("byright-worker", "render", "private"),
    }
    assert all(
        service.plan != "free" and service.tls == "required"
        for service in manifest.deployment.services
    )
    assert all(
        assertion.version == "1.0"
        and assertion.algorithm == "Ed25519"
        and assertion.kid
        and len(assertion.payload_sha256) == 64
        and len(assertion.signature) == 86
        and assertion.expires_at - assertion.issued_at <= timedelta(minutes=5)
        for assertion in (service.service_assertion for service in manifest.deployment.services)
    )
    assert manifest.database.provider == "neon"
    assert manifest.database.network_access == "private"
    assert manifest.object_store.access == "private"
    assert manifest.object_store.immutability == "object-lock"


def test_governance_contract_names_owners_recovery_and_customer_rules() -> None:
    manifest = ReleaseManifest.model_validate_json(ARCHITECTURE.read_text(encoding="utf-8"))

    assert {schema.role for schema in manifest.database.schemas} == {
        "plotlot_app",
        "byright_engine",
    }
    assert manifest.database.backup.model_dump() == {
        "enabled": True,
        "pitr": True,
        "restore_owner": "Platform Operations",
        "rpo_minutes": 15,
        "rto_hours": 4,
    }
    assert all(secret.owner for secret in manifest.secrets)
    assert all(policy.rights_basis for policy in manifest.governance.data_policies)
    assert all(
        policy.retention_days is not None and policy.retention_days > 0
        for policy in manifest.governance.data_policies
    )
    assert all(policy.deletion_owner for policy in manifest.governance.data_policies)
    assert manifest.governance.entitlements.mode == "manual"
    assert manifest.governance.dedicated_deployments.model_dump() == {
        "code_fork": False,
        "digest_parity": True,
        "schema_parity": True,
        "setup": "paid",
    }
    assert manifest.governance.incident.owner
    assert manifest.governance.incident.rollback_owner
    assert {(slo.name, slo.target, slo.owner) for slo in manifest.governance.slos} == {
        ("availability", "99.5% monthly", "Platform Operations"),
        ("first-event", "p95 <= 2s", "Platform Operations"),
        ("queue-start", "p95 <= 10s", "Workflow Operations"),
        (
            "terminal-analysis",
            "p95 <= 120s; p99 <= 180s at concurrency 2",
            "Workflow Operations",
        ),
        ("evidence-durability", "99.999999999%", "Compliance Owner"),
    }


def test_release_manifest_schema_requires_signature_and_contract_binding() -> None:
    schema = SCHEMA_ADAPTER.validate_json(SCHEMA.read_text(encoding="utf-8"))

    assert schema["$id"] == "https://plotlot.app/schemas/release-manifest-v1.json"
    assert {"contracts", "signature"}.issubset(schema["required"])
    assert schema["$defs"]["Signature"]["required"] == [
        "algorithm",
        "key_id",
        "signed_by",
        "payload_sha256",
        "value",
    ]
    assert schema["$defs"]["ServiceAssertion"]["required"] == [
        "version",
        "algorithm",
        "audience",
        "issuer",
        "key_owner",
        "kid",
        "payload_sha256",
        "signature",
        "issued_at",
        "expires_at",
    ]
