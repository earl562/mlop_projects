#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

from pair_gate_checks import (
    parse_report,
    scan_artifacts,
    verify_bindings,
    verify_release_artifacts,
    verify_repository,
    verify_test_policy_bindings,
)
from pair_gate_types import (
    GateError,
    JsonObject,
    JsonValue,
    gate_error,
    require_int,
    require_list,
    require_object,
    require_path,
    require_string,
)


def canonical(value: JsonValue) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load_manifest(path: Path) -> JsonObject:
    try:
        value: JsonValue = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise gate_error("PAIR_E_MANIFEST", f"cannot load manifest: {error}") from error
    manifest = require_object(value, "manifest")
    if manifest.get("schema") != "RepositoryPairV1":
        raise gate_error("PAIR_E_MANIFEST", "schema must be RepositoryPairV1")
    unsigned = dict(manifest)
    signature = require_string(unsigned.pop("signature", None), "signature")
    integrity = require_string(unsigned.pop("integritySha256", None), "integritySha256")
    if hashlib.sha256(canonical(unsigned)).hexdigest() != integrity:
        raise gate_error("PAIR_E_MANIFEST", "canonical integrity mismatch")
    key = os.environ.get("PAIR_MANIFEST_SIGNING_KEY")
    if key is None:
        raise gate_error("PAIR_E_SIGNATURE", "PAIR_MANIFEST_SIGNING_KEY is required")
    expected = hmac.new(key.encode(), integrity.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise gate_error("PAIR_E_SIGNATURE", "manifest signature mismatch")
    return manifest


def run_lane(
    lane: JsonObject,
    repositories: dict[str, Path],
    artifact_root: Path,
) -> JsonObject:
    lane_id = require_string(lane.get("id"), "lane.id")
    repository = require_string(lane.get("repository"), "lane.repository")
    command = [
        require_string(value, "lane command")
        for value in require_list(lane.get("command"), "lane.command")
    ]
    if repository not in repositories:
        raise gate_error("PAIR_E_MANIFEST", f"unknown lane repository: {repository}")
    working_directory = repositories[repository]
    relative_cwd = lane.get("cwd")
    if relative_cwd is not None:
        working_directory = working_directory / require_string(relative_cwd, "lane.cwd")
    environment = os.environ.copy()
    raw_environment = lane.get("environment")
    if raw_environment is not None:
        for key, value in require_object(raw_environment, "lane.environment").items():
            environment[key] = require_string(value, f"lane.environment.{key}")
    logs = artifact_root / "commands"
    logs.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        command,
        cwd=working_directory,
        env=environment,
        check=False,
        capture_output=True,
        timeout=require_lane_timeout(lane),
    )
    output = result.stdout + result.stderr
    log_path = logs / f"{lane_id}.log"
    log_path.write_bytes(output)
    if result.returncode != 0:
        raise gate_error("PAIR_E_COMMAND", f"{lane_id} exited {result.returncode}")
    test_count = 0
    skipped = 0
    report_value = lane.get("report")
    if report_value is not None:
        test_count, skipped = parse_report(
            require_object(report_value, "lane.report"), artifact_root
        )
        if skipped:
            raise gate_error("PAIR_E_SKIPPED_TEST", f"{lane_id} skipped {skipped} tests")
        if test_count == 0:
            raise gate_error("PAIR_E_ZERO_TEST", f"{lane_id} discovered zero tests")
        expected_count = lane.get("expectedTestCount")
        if expected_count is not None:
            required_count = require_int(expected_count, "lane.expectedTestCount")
        else:
            required_count = None
        if required_count is not None and test_count != required_count:
            raise gate_error(
                "PAIR_E_STALE_EVIDENCE",
                f"{lane_id} expected {required_count} tests but recorded {test_count}",
            )
    browser_glob = lane.get("browserArtifactGlob")
    if browser_glob is not None:
        pattern = require_string(browser_glob, "lane.browserArtifactGlob")
        if not any(path.is_file() for path in artifact_root.glob(pattern)):
            raise gate_error("PAIR_E_BROWSER_ARTIFACT", f"{lane_id} browser artifact missing")
    command_evidence: list[JsonValue] = [value for value in command]
    return {
        "id": lane_id,
        "repository": repository,
        "command": command_evidence,
        "exitCode": result.returncode,
        "testCount": test_count,
        "skipped": skipped,
        "logSha256": hashlib.sha256(output).hexdigest(),
    }


def require_lane_timeout(lane: JsonObject) -> float:
    value = lane.get("timeoutSeconds")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise gate_error("PAIR_E_MANIFEST", "lane.timeoutSeconds must be positive")
    return float(value)


def verify(args: argparse.Namespace) -> None:
    plotlot = Path(args.plotlot_clone).resolve()
    byright = Path(args.byright_clone).resolve()
    manifest = load_manifest(Path(args.manifest).resolve())
    repositories = {"plotlot": plotlot, "byright": byright}
    gate = require_object(manifest.get("releaseGate"), "releaseGate")
    artifact_root = require_path(gate.get("artifactRoot"), "releaseGate.artifactRoot")
    if any(
        artifact_root == repo or artifact_root.is_relative_to(repo)
        for repo in repositories.values()
    ):
        raise gate_error("PAIR_E_ARTIFACT_ROOT", "artifact root must be outside both repositories")
    artifact_root.mkdir(parents=True, exist_ok=True)
    verify_test_policy_bindings(gate)
    manifest_repositories = require_object(manifest.get("repositories"), "repositories")
    for name, repo in repositories.items():
        entry = require_object(manifest_repositories.get(name), f"repositories.{name}")
        verify_repository(repo, require_string(entry.get("head"), f"{name}.head"))
    verify_bindings(repositories, gate)
    lane_receipts: list[JsonValue] = []
    if args.full:
        for value in require_list(gate.get("lanes"), "releaseGate.lanes"):
            lane_receipts.append(
                run_lane(require_object(value, "lane"), repositories, artifact_root)
            )
        verify_bindings(repositories, gate)
        for name, repo in repositories.items():
            entry = require_object(manifest_repositories.get(name), f"repositories.{name}")
            verify_repository(repo, require_string(entry.get("head"), f"{name}.head"))
    verify_release_artifacts(artifact_root, gate)
    scan_artifacts(artifact_root, gate)
    evidence = {
        "schema": "RepositoryPairEvidenceV1",
        "plotlotSha": require_object(manifest_repositories["plotlot"], "plotlot").get("head"),
        "byrightSha": require_object(manifest_repositories["byright"], "byright").get("head"),
        "lanes": lane_receipts,
        "status": "passed",
    }
    evidence_path = artifact_root / "repository-pair-evidence.json"
    evidence_path.write_bytes(canonical(evidence) + b"\n")
    print(f"PAIR_VALIDATION_OK=true evidence={evidence_path}")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--plotlot-clone", required=True)
    value.add_argument("--byright-clone", required=True)
    value.add_argument("--manifest", required=True)
    value.add_argument("--full", action="store_true")
    return value


def main() -> int:
    try:
        verify(parser().parse_args())
    except GateError as error:
        print(f"PAIR_GATE_FAILED code={error.code} detail={error}", file=sys.stderr)
        return error.exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
