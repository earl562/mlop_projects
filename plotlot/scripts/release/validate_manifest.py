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

from pydantic import ValidationError

from release_contract import ReleaseCandidate


Policy = tuple[str, Callable[[ReleaseCandidate], bool]]


def validation_error_code(error: ValidationError) -> str:
    assertion_errors = [detail for detail in error.errors() if "service_assertion" in detail["loc"]]
    if not assertion_errors:
        return "MANIFEST_SCHEMA_INVALID"
    if all(
        detail["type"] == "missing" and detail["loc"][-1] == "signature"
        for detail in assertion_errors
    ):
        return "SERVICE_ASSERTION_UNSIGNED"
    if any(
        detail["type"] in {"service_assertion_deadline", "service_assertion_lifetime"}
        for detail in assertion_errors
    ):
        return "SERVICE_ASSERTION_WINDOW_INVALID"
    return "SERVICE_ASSERTION_INVALID"


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
    except OSError as error:
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
    except ValidationError as error:
        code = validation_error_code(error)
        print(
            json.dumps(
                {
                    "codes": [code],
                    "detail": str(error),
                    "manifest": os.path.relpath(path, Path.cwd()),
                    "valid": False,
                },
                sort_keys=True,
            )
        )
        return 2 if code == "MANIFEST_SCHEMA_INVALID" else 1

    codes = policy_results(manifest)
    print(report(path, codes))
    return 1 if codes else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
