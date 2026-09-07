from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "release" / "validate_manifest.py"
FIXTURES = ROOT / "tests" / "fixtures" / "release"
POISON_CODES = {
    "free-plan.json": "PROD_FREE_PLAN",
    "public-database.json": "DATABASE_PUBLIC",
    "no-tls.json": "TLS_REQUIRED",
    "missing-secret-owner.json": "SECRET_OWNER_REQUIRED",
    "shared-database-role.json": "DATABASE_ROLE_ISOLATION",
    "no-backup.json": "BACKUP_PITR_REQUIRED",
    "rpo-breach.json": "RPO_BREACH",
    "rto-breach.json": "RTO_BREACH",
    "missing-retention.json": "RETENTION_POLICY_REQUIRED",
    "contract-hash-mismatch.json": "CONTRACT_HASH_MISMATCH",
    "customer-fork.json": "CUSTOMER_CODE_FORK_FORBIDDEN",
    "unsigned-release.json": "RELEASE_SIGNATURE_REQUIRED",
    "unsigned-service-assertion.json": "SERVICE_ASSERTION_UNSIGNED",
    "invalid-service-assertion.json": "SERVICE_ASSERTION_INVALID",
    "unbounded-service-assertion.json": "SERVICE_ASSERTION_WINDOW_INVALID",
}


def run_validator(fixture: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(FIXTURES / fixture)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_valid_release_manifest_is_accepted() -> None:
    result = run_validator("valid.json")

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "codes": [],
        "manifest": "tests/fixtures/release/valid.json",
        "valid": True,
    }


@pytest.mark.parametrize(("fixture", "policy_code"), POISON_CODES.items())
def test_poison_release_manifest_is_rejected_with_exact_policy_code(
    fixture: str,
    policy_code: str,
) -> None:
    result = run_validator(fixture)

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["valid"] is False
    assert report["codes"] == [policy_code]
