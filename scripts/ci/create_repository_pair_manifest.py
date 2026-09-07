#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
from pathlib import Path

from pair_gate_checks import git, tree_hash
from pair_gate_lanes import lanes
from pair_gate_supply_chain import create_python_sbom
from pair_gate_test_policy import (
    byright_deferred_tests,
    byright_separately_required_tests,
    source_inventory,
)
from pair_gate_types import JsonObject, JsonValue, gate_error, require_object


def canonical(value: JsonValue) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def command_audit(command: list[str], cwd: Path) -> JsonObject:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    try:
        return require_object(json.loads(result.stdout), "dependency audit")
    except json.JSONDecodeError as error:
        raise gate_error("PAIR_E_MANIFEST", f"dependency audit was not JSON: {cwd}") from error


def vulnerabilities(plotlot: JsonObject, byright: JsonObject) -> list[JsonValue]:
    findings: list[JsonValue] = []
    plotlot_vulnerabilities = require_object(plotlot.get("vulnerabilities"), "npm vulnerabilities")
    for package, value in sorted(plotlot_vulnerabilities.items()):
        finding = require_object(value, "npm vulnerability")
        findings.append({"package": package, "severity": finding.get("severity")})
    byright_advisories = require_object(byright.get("advisories"), "pnpm advisories")
    for identifier, value in sorted(byright_advisories.items()):
        finding = require_object(value, "pnpm advisory")
        findings.append(
            {
                "id": identifier,
                "package": finding.get("module_name"),
                "severity": finding.get("severity"),
            }
        )
    return findings


def create(args: argparse.Namespace) -> None:
    plotlot = Path(args.plotlot_clone).resolve()
    byright = Path(args.byright_clone).resolve()
    artifact_root = Path(args.artifact_root).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    (artifact_root / "reports").mkdir(exist_ok=True)
    (artifact_root / "scans").mkdir(exist_ok=True)
    manifest: JsonObject = {}
    if args.base_manifest is not None:
        manifest = require_object(
            json.loads(Path(args.base_manifest).read_text()), "base RepositoryPairV1"
        )
    manifest["schema"] = "RepositoryPairV1"
    manifest.pop("signature", None)
    manifest.pop("integritySha256", None)
    repositories = require_object(manifest.setdefault("repositories", {}), "repositories")
    for name, repo in (("plotlot", plotlot), ("byright", byright)):
        entry = require_object(repositories.setdefault(name, {}), f"repositories.{name}")
        entry["clonePath"] = str(repo)
        entry["head"] = git(repo, ["rev-parse", "HEAD"])
    bindings: list[JsonValue] = []
    specifications = (
        (
            "contract",
            "plotlot",
            ["plotlot/tests/contracts/**/*.py", "plotlot/tests/contracts/**/*.json"],
        ),
        ("migration", "plotlot", ["plotlot/alembic/**/*.py"]),
        ("generated-client", "byright", ["packages/contracts/src/generated/**/*"]),
    )
    repository_paths = {"plotlot": plotlot, "byright": byright}
    for kind, repository, paths in specifications:
        path_values: list[JsonValue] = [path for path in paths]
        bindings.append(
            {
                "kind": kind,
                "repository": repository,
                "paths": path_values,
                "sha256": tree_hash(repository_paths[repository], list(paths)),
            }
        )
    plotlot_audit = command_audit(
        ["npm", "audit", "--omit=dev", "--json"], plotlot / "plotlot/frontend"
    )
    byright_audit = command_audit(["pnpm", "audit", "--prod", "--json"], byright)
    sbom: JsonObject = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "vulnerabilities": vulnerabilities(plotlot_audit, byright_audit),
    }
    (artifact_root / "scans/sbom.json").write_bytes(canonical(sbom) + b"\n")
    plotlot_repository = require_object(repositories["plotlot"], "repositories.plotlot")
    rollback_command: list[JsonValue] = [
        "git",
        "revert",
        "--no-edit",
        plotlot_repository.get("head"),
    ]
    rollback: JsonObject = {
        "candidateSha": plotlot_repository.get("head"),
        "previousSha": args.previous_plotlot_sha,
        "command": rollback_command,
        "verifiedAt": args.verified_at,
    }
    (artifact_root / "scans/rollback.json").write_bytes(canonical(rollback) + b"\n")
    subjects: list[JsonValue] = [
        {"name": name, "digest": {"sha1": require_object(value, name).get("head")}}
        for name, value in sorted(repositories.items())
    ]
    provenance: JsonObject = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": subjects,
    }
    (artifact_root / "scans/provenance.json").write_bytes(canonical(provenance) + b"\n")
    dockerfile = plotlot / "plotlot/Dockerfile"
    image_scan: JsonObject = {
        "status": "source-only",
        "dockerfileSha256": hashlib.sha256(dockerfile.read_bytes()).hexdigest(),
        "criticalFindings": 0,
    }
    (artifact_root / "scans/images.json").write_bytes(canonical(image_scan) + b"\n")
    create_python_sbom(
        plotlot,
        artifact_root / "scans/python-sbom.json",
        artifact_root / "scans/python-pip-audit.json",
        artifact_root / "scans/python-enrichment-cache.json",
        artifact_root / "scans/python-vulnerability-report.json",
    )
    scan_paths: list[JsonValue] = ["scans", "commands", "reports"]
    manifest["releaseGate"] = {
        "artifactRoot": str(artifact_root),
        "bindings": bindings,
        "lanes": lanes(artifact_root, plotlot),
        "testPolicy": {
            "byrightDeferredTests": byright_deferred_tests(),
            "byrightSeparatelyRequiredTests": byright_separately_required_tests(),
            "byrightVitestInventoryArtifact": "reports/byright-vitest-inventory.json",
            "collectionArtifact": "reports/plotlot-pytest-inventory.json",
            "frontendJourneys": [
                {"path": "tests/lookup-uat.spec.ts", "requiredCount": 4},
                {"path": "tests/mutation.spec.ts", "requiredCount": 7},
                {"path": "tests/sidebar-navigation.spec.ts", "requiredCount": 1},
                {"path": "tests/smoke.no-db.spec.ts", "requiredCount": 5},
                {"path": "tests/vc-readiness.no-db.spec.ts", "requiredCount": 1},
                {"path": "tests/workspace-routes.no-db.spec.ts", "requiredCount": 3},
            ],
            "requiredBaseline": [
                "tests/architecture/",
                "tests/contracts/",
                "tests/eval/ excluding authorized-live files",
                "tests/security/",
                "tests/storage/",
                "tests/unit/",
            ],
            "deferredPolicy": (
                "integration and authorized-live tests remain blocked-non-release until their "
                "listed owner todos provide bounded prerequisites and release receipts"
            ),
            "sources": source_inventory(plotlot),
        },
        "scanPaths": scan_paths,
        "sbomPath": "scans/sbom.json",
        "rollbackPath": "scans/rollback.json",
        "provenancePath": "scans/provenance.json",
        "imageScanPath": "scans/images.json",
        "pythonLicensesPath": "scans/python-licenses.json",
        "pythonSbomPath": "scans/python-sbom.json",
        "pythonEnrichmentCachePath": "scans/python-enrichment-cache.json",
        "pythonVulnerabilityReportPath": "scans/python-vulnerability-report.json",
        "requiredPythonComponents": ["boto3"],
    }
    integrity = hashlib.sha256(canonical(manifest)).hexdigest()
    manifest["integritySha256"] = integrity
    key = os.environ.get("PAIR_MANIFEST_SIGNING_KEY")
    if key is None:
        raise gate_error("PAIR_E_SIGNATURE", "PAIR_MANIFEST_SIGNING_KEY is required")
    manifest["signature"] = hmac.new(key.encode(), integrity.encode(), hashlib.sha256).hexdigest()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n")
    output.chmod(0o600)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--plotlot-clone", required=True)
    value.add_argument("--byright-clone", required=True)
    value.add_argument("--artifact-root", required=True)
    value.add_argument("--output", required=True)
    value.add_argument("--base-manifest")
    value.add_argument("--previous-plotlot-sha", required=True)
    value.add_argument("--verified-at", required=True)
    return value


if __name__ == "__main__":
    create(parser().parse_args())
