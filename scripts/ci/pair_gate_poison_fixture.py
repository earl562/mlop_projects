from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pair_gate_checks import tree_hash
from pair_gate_types import JsonObject, JsonValue

KEY = "repository-pair-test-signing-key"


def canonical(value: JsonValue) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def make_repo(path: Path, kind: str) -> None:
    path.mkdir()
    (path / "package.json").write_text('{"private":true}\n')
    if kind == "plotlot":
        (path / "contracts").mkdir()
        (path / "contracts/schema.json").write_text('{"version":1}\n')
        (path / "migrations").mkdir()
        (path / "migrations/001.sql").write_text("select 1;\n")
    else:
        (path / "client").mkdir()
        (path / "client/index.ts").write_text('export const version = "1"\n')
    git(path, "init", "-q")
    git(path, "config", "user.name", "Pair Gate Test")
    git(path, "config", "user.email", "pair-gate@example.invalid")
    git(path, "add", ".")
    git(path, "commit", "-qm", "baseline")


def sign(manifest: JsonObject) -> None:
    manifest.pop("integritySha256", None)
    manifest.pop("signature", None)
    integrity = hashlib.sha256(canonical(manifest)).hexdigest()
    manifest["integritySha256"] = integrity
    manifest["signature"] = hmac.new(KEY.encode(), integrity.encode(), hashlib.sha256).hexdigest()


def base_manifest(plotlot: Path, byright: Path, artifacts: Path) -> JsonObject:
    scans = artifacts / "scans"
    scans.mkdir(parents=True)
    (scans / "content.json").write_text('{"classification":"redacted"}\n')
    (scans / "sbom.json").write_text(
        '{"bomFormat":"CycloneDX","specVersion":"1.6","vulnerabilities":[]}\n'
    )
    (scans / "rollback.json").write_text(
        '{"candidateSha":"a","previousSha":"b","command":["rollback"],'
        '"verifiedAt":"2026-07-26T00:00:00Z"}\n'
    )
    (scans / "provenance.json").write_text('{"predicateType":"https://slsa.dev/provenance/v1"}\n')
    (scans / "images.json").write_text('{"status":"source-only","criticalFindings":0}\n')
    (scans / "python-sbom.json").write_text(
        '{"bomFormat":"CycloneDX","components":[{"name":"boto3"}],"vulnerabilities":[]}\n'
    )
    (scans / "python-licenses.json").write_text(
        '{"packages":[{"name":"boto3","license":"Apache-2.0"}]}\n'
    )
    cache: JsonObject = {
        "schema": "PythonVulnerabilityEnrichmentCacheV1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": {"osv": {"status": "available"}, "cisaKev": {"status": "available"}},
        "osv": [],
        "kevCveIds": [],
    }
    (scans / "python-enrichment-cache.json").write_bytes(canonical(cache) + b"\n")
    report: JsonObject = {
        "schema": "PythonVulnerabilityReportV1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "maxAgeHours": 24,
        "enrichmentStatus": "available",
        "cacheSha256": hashlib.sha256(
            (scans / "python-enrichment-cache.json").read_bytes()
        ).hexdigest(),
        "findingCount": 0,
        "findings": [],
    }
    (scans / "python-vulnerability-report.json").write_bytes(canonical(report) + b"\n")
    value: JsonObject = {
        "schema": "RepositoryPairV1",
        "repositories": {
            "plotlot": {"head": git(plotlot, "rev-parse", "HEAD")},
            "byright": {"head": git(byright, "rev-parse", "HEAD")},
        },
        "releaseGate": {
            "artifactRoot": str(artifacts),
            "bindings": [
                {
                    "kind": "contract",
                    "repository": "plotlot",
                    "paths": ["contracts/*.json"],
                    "sha256": tree_hash(plotlot, ["contracts/*.json"]),
                },
                {
                    "kind": "migration",
                    "repository": "plotlot",
                    "paths": ["migrations/*.sql"],
                    "sha256": tree_hash(plotlot, ["migrations/*.sql"]),
                },
                {
                    "kind": "generated-client",
                    "repository": "byright",
                    "paths": ["client/*.ts"],
                    "sha256": tree_hash(byright, ["client/*.ts"]),
                },
            ],
            "lanes": [],
            "scanPaths": ["scans/content.json"],
            "sbomPath": "scans/sbom.json",
            "rollbackPath": "scans/rollback.json",
            "provenancePath": "scans/provenance.json",
            "imageScanPath": "scans/images.json",
            "pythonLicensesPath": "scans/python-licenses.json",
            "pythonSbomPath": "scans/python-sbom.json",
            "pythonEnrichmentCachePath": "scans/python-enrichment-cache.json",
            "pythonVulnerabilityReportPath": "scans/python-vulnerability-report.json",
            "requiredPythonComponents": ["boto3"],
        },
    }
    sign(value)
    return value
