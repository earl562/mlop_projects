from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree

from pair_gate_types import (
    JsonObject,
    JsonValue,
    gate_error,
    require_int,
    require_list,
    require_object,
    require_string,
)
from pair_gate_supply_chain import verify_python_supply_chain

DEPENDENCY_PATHS = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "uv.lock",
}
SECRET_PATTERN = re.compile(
    rb"(?:sk_(?:live|test)_[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{20,}|"
    rb"AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)
PII_PATTERN = re.compile(
    rb"(?:\b\d{3}-\d{2}-\d{4}\b|"
    rb"\b[A-Z0-9._%+-]+@(?!example\.(?:invalid|test)\b)[A-Z0-9.-]+\.[A-Z]{2,}\b)",
    re.IGNORECASE,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(root: Path, paths: list[JsonValue]) -> str:
    digest = hashlib.sha256()
    matched = 0
    for raw in sorted(require_string(item, "binding path") for item in paths):
        candidates = sorted(root.glob(raw))
        for candidate in candidates:
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root).as_posix()
            digest.update(relative.encode())
            digest.update(b"\0")
            digest.update(candidate.read_bytes())
            digest.update(b"\0")
            matched += 1
    if matched == 0:
        raise gate_error("PAIR_E_MANIFEST", "binding path set matched no files")
    return digest.hexdigest()


def git(repo: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise gate_error("PAIR_E_MANIFEST", result.stderr.strip() or "git failed")
    return result.stdout.strip()


def verify_repository(repo: Path, expected_sha: str) -> None:
    if git(repo, ["rev-parse", "HEAD"]) != expected_sha:
        raise gate_error("PAIR_E_SHA", f"{repo.name} is not at its pinned SHA")
    status = git(repo, ["status", "--porcelain=v1", "--untracked-files=all"])
    dirty_paths = [line[2:].strip() for line in status.splitlines() if len(line) > 2]
    if any(Path(path).name in DEPENDENCY_PATHS for path in dirty_paths):
        raise gate_error("PAIR_E_DIRTY_DEPENDENCY", f"{repo.name} dependency state is dirty")
    if dirty_paths:
        raise gate_error("PAIR_E_DIRTY_TREE", f"{repo.name} working tree is dirty")


def verify_bindings(repositories: dict[str, Path], gate: JsonObject) -> None:
    bindings = require_list(gate.get("bindings"), "releaseGate.bindings")
    code_by_kind = {
        "contract": "PAIR_E_CONTRACT_DRIFT",
        "migration": "PAIR_E_MIGRATION_DRIFT",
        "generated-client": "PAIR_E_CLIENT_DRIFT",
    }
    seen: set[str] = set()
    for value in bindings:
        binding = require_object(value, "binding")
        kind = require_string(binding.get("kind"), "binding.kind")
        repository = require_string(binding.get("repository"), "binding.repository")
        expected = require_string(binding.get("sha256"), "binding.sha256")
        if kind not in code_by_kind or repository not in repositories:
            raise gate_error("PAIR_E_MANIFEST", "unsupported binding")
        actual = tree_hash(
            repositories[repository],
            require_list(binding.get("paths"), "binding.paths"),
        )
        if actual != expected:
            raise gate_error(code_by_kind[kind], f"{kind} hash mismatch")
        seen.add(kind)
    if seen != set(code_by_kind):
        raise gate_error("PAIR_E_MANIFEST", "all binding kinds are required")


def verify_test_policy_bindings(gate: JsonObject) -> None:
    test_policy = require_object(gate.get("testPolicy", {}), "releaseGate.testPolicy")
    policy_entries = require_list(
        test_policy.get("byrightSeparatelyRequiredTests", []),
        "testPolicy.byrightSeparatelyRequiredTests",
    )
    lanes = [
        require_object(value, "lane")
        for value in require_list(gate.get("lanes", []), "releaseGate.lanes")
    ]
    lanes_by_id = {require_string(lane.get("id"), "lane.id"): lane for lane in lanes}
    policy_bindings: dict[str, str] = {}
    for raw_entry in policy_entries:
        entry = require_object(raw_entry, "separately required test")
        title = require_string(entry.get("title"), "separately required test.title")
        lane_id = require_string(entry.get("lane"), "separately required test.lane")
        if entry.get("releaseStatus") != "required" or title in policy_bindings:
            raise gate_error("PAIR_E_MANIFEST", "invalid separately required test policy")
        lane = lanes_by_id.get(lane_id)
        if lane is None:
            raise gate_error("PAIR_E_MANIFEST", "separately required test lane is missing")
        report = require_object(lane.get("report"), f"{lane_id}.report")
        required_passed = {
            require_string(value, "required passed test")
            for value in require_list(
                report.get("requiredPassedTests", []), f"{lane_id}.requiredPassedTests"
            )
        }
        if title not in required_passed:
            raise gate_error("PAIR_E_MANIFEST", "separately required test is not bound to its lane")
        policy_bindings[title] = lane_id
    referenced_titles: set[str] = set()
    for lane in lanes:
        report_value = lane.get("report")
        if report_value is None:
            continue
        report = require_object(report_value, "lane.report")
        referenced_titles.update(
            require_string(value, "separately required test")
            for value in require_list(
                report.get("separatelyRequiredTests", []),
                "report.separatelyRequiredTests",
            )
        )
    if referenced_titles != set(policy_bindings):
        raise gate_error("PAIR_E_MANIFEST", "separately required test policy binding mismatch")


def parse_report(report: JsonObject, artifact_root: Path) -> tuple[int, int]:
    report_format = require_string(report.get("format"), "report.format")
    path = artifact_root / require_string(report.get("path"), "report.path")
    if not path.is_file():
        raise gate_error("PAIR_E_ZERO_TEST", f"missing structured report: {path.name}")
    if report_format == "junit":
        root = ElementTree.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        return (
            sum(int(suite.attrib.get("tests", "0")) for suite in suites),
            sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
        )
    value = json.loads(path.read_text())
    if report_format == "vitest-list":
        return len(require_list(value, "Vitest inventory")), 0
    parsed = require_object(value, "test report")
    if report_format == "vitest":
        expected_deferred = sorted(
            require_string(value, "deferred test")
            for value in require_list(
                report.get("deferredSkippedTests", []), "report.deferredSkippedTests"
            )
        )
        separately_required = sorted(
            require_string(value, "separately required test")
            for value in require_list(
                report.get("separatelyRequiredTests", []), "report.separatelyRequiredTests"
            )
        )
        required_passed = sorted(
            require_string(value, "required passed test")
            for value in require_list(
                report.get("requiredPassedTests", []), "report.requiredPassedTests"
            )
        )
        if not expected_deferred and not separately_required and not required_passed:
            return (
                require_int(parsed.get("numTotalTests"), "numTotalTests"),
                require_int(parsed.get("numPendingTests"), "numPendingTests"),
            )
        actual_skipped: list[str] = []
        actual_passed: list[str] = []
        for raw_result in require_list(parsed.get("testResults"), "testResults"):
            test_result = require_object(raw_result, "test result")
            for raw_assertion in require_list(
                test_result.get("assertionResults"), "assertionResults"
            ):
                assertion = require_object(raw_assertion, "assertion")
                status = assertion.get("status")
                if status not in {"passed", "skipped"}:
                    continue
                titles = [
                    require_string(title, "ancestor title")
                    for title in require_list(assertion.get("ancestorTitles"), "ancestorTitles")
                ]
                titles.append(require_string(assertion.get("title"), "test title"))
                full_title = " > ".join(titles)
                if status == "skipped":
                    actual_skipped.append(full_title)
                else:
                    actual_passed.append(full_title)
        expected_skipped = sorted(expected_deferred + separately_required)
        if sorted(actual_skipped) != expected_skipped:
            raise gate_error(
                "PAIR_E_SKIPPED_TEST",
                "Vitest skipped-test inventory differs from signed deferred policy",
            )
        if not set(required_passed).issubset(actual_passed):
            raise gate_error(
                "PAIR_E_STALE_EVIDENCE",
                "required separately-executed Vitest test did not pass",
            )
        return (
            require_int(parsed.get("numTotalTests"), "numTotalTests") - len(actual_skipped),
            0,
        )
    if report_format == "playwright":
        stats = require_object(parsed.get("stats"), "stats")
        total = sum(
            require_int(stats.get(key), f"stats.{key}")
            for key in ("expected", "unexpected", "flaky", "skipped")
        )
        return total, require_int(stats.get("skipped"), "stats.skipped")
    if report_format == "collection":
        return (
            require_int(parsed.get("total"), "total"),
            require_int(parsed.get("skipped"), "skipped"),
        )
    raise gate_error("PAIR_E_MANIFEST", f"unsupported report format: {report_format}")


def scan_artifacts(artifact_root: Path, gate: JsonObject) -> None:
    scan_paths = [
        artifact_root / require_string(value, "scan path")
        for value in require_list(gate.get("scanPaths"), "releaseGate.scanPaths")
    ]
    files = sorted(
        path
        for scan_path in scan_paths
        for path in ([scan_path] if scan_path.is_file() else scan_path.rglob("*"))
        if path.is_file()
    )
    for path in files:
        payload = path.read_bytes()
        if SECRET_PATTERN.search(payload):
            raise gate_error("PAIR_E_SECRET", "secret-shaped value found in release evidence")
        if PII_PATTERN.search(payload) or b"RAW_LICENSED_DATA" in payload:
            raise gate_error("PAIR_E_PRIVACY", "PII or raw licensed data found in release evidence")
        if b'"compositionMode":"live"' in payload and b'"fixture"' in payload:
            raise gate_error("PAIR_E_FIXTURE_LIVE", "fixture/live evidence contamination found")


def verify_release_artifacts(artifact_root: Path, gate: JsonObject) -> None:
    verify_python_supply_chain(artifact_root, gate)
    sbom_path = artifact_root / require_string(gate.get("sbomPath"), "releaseGate.sbomPath")
    sbom = require_object(json.loads(sbom_path.read_text()), "SBOM")
    vulnerabilities = require_list(sbom.get("vulnerabilities"), "SBOM vulnerabilities")
    for value in vulnerabilities:
        vulnerability = require_object(value, "SBOM vulnerability")
        if (
            require_string(vulnerability.get("severity"), "vulnerability.severity").lower()
            == "critical"
        ):
            raise gate_error("PAIR_E_SBOM_CRITICAL", "critical SBOM finding")
    rollback_path = artifact_root / require_string(
        gate.get("rollbackPath"), "releaseGate.rollbackPath"
    )
    rollback = require_object(json.loads(rollback_path.read_text()), "rollback metadata")
    required_rollback = {"candidateSha", "previousSha", "command", "verifiedAt"}
    if not required_rollback.issubset(rollback):
        raise gate_error("PAIR_E_ROLLBACK", "rollback metadata is incomplete")
    provenance_path = artifact_root / require_string(
        gate.get("provenancePath"), "releaseGate.provenancePath"
    )
    provenance = require_object(json.loads(provenance_path.read_text()), "provenance")
    if provenance.get("predicateType") != "https://slsa.dev/provenance/v1":
        raise gate_error("PAIR_E_PROVENANCE", "SLSA provenance is missing")
    image_path = artifact_root / require_string(
        gate.get("imageScanPath"), "releaseGate.imageScanPath"
    )
    image_scan = require_object(json.loads(image_path.read_text()), "image scan")
    if image_scan.get("status") not in {"source-only", "scanned"}:
        raise gate_error("PAIR_E_PROVENANCE", "image scan metadata is missing")
