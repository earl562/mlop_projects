#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias, assert_never

from pair_gate_poison_fixture import KEY, base_manifest, make_repo, sign
from pair_gate_types import JsonObject, JsonValue

PoisonName: TypeAlias = Literal[
    "contract-drift",
    "migration-drift",
    "generated-client-drift",
    "wrong-sha",
    "dirty-dependency",
    "skipped-test",
    "zero-test",
    "missing-browser-artifact",
    "fixture-live-contamination",
    "secret-shape",
    "pii-raw-licensed-data",
    "sbom-critical-finding",
    "sbom-kev-finding",
    "sbom-direct-fixable",
    "sbom-enrichment-stale",
    "missing-rollback-metadata",
]
POISONS: dict[PoisonName, str] = {
    "contract-drift": "PAIR_E_CONTRACT_DRIFT",
    "migration-drift": "PAIR_E_MIGRATION_DRIFT",
    "generated-client-drift": "PAIR_E_CLIENT_DRIFT",
    "wrong-sha": "PAIR_E_SHA",
    "dirty-dependency": "PAIR_E_DIRTY_DEPENDENCY",
    "skipped-test": "PAIR_E_SKIPPED_TEST",
    "zero-test": "PAIR_E_ZERO_TEST",
    "missing-browser-artifact": "PAIR_E_BROWSER_ARTIFACT",
    "fixture-live-contamination": "PAIR_E_FIXTURE_LIVE",
    "secret-shape": "PAIR_E_SECRET",
    "pii-raw-licensed-data": "PAIR_E_PRIVACY",
    "sbom-critical-finding": "PAIR_E_SBOM_CRITICAL",
    "sbom-kev-finding": "PAIR_E_SBOM_KEV",
    "sbom-direct-fixable": "PAIR_E_SBOM_DIRECT_FIXABLE",
    "sbom-enrichment-stale": "PAIR_E_SBOM_ENRICHMENT",
    "missing-rollback-metadata": "PAIR_E_ROLLBACK",
}


@dataclass(frozen=True, slots=True)
class PoisonFixture:
    manifest: JsonObject
    plotlot: Path
    byright: Path
    artifacts: Path


def binding(manifest: JsonObject, kind: str) -> JsonObject:
    gate = manifest["releaseGate"]
    assert isinstance(gate, dict)
    bindings = gate["bindings"]
    assert isinstance(bindings, list)
    for value in bindings:
        assert isinstance(value, dict)
        if value.get("kind") == kind:
            return value
    raise AssertionError(kind)


def set_lane(manifest: JsonObject, command: str, report: str, browser: bool = False) -> None:
    gate = manifest["releaseGate"]
    assert isinstance(gate, dict)
    lane: JsonObject = {
        "id": "poison",
        "repository": "plotlot",
        "command": [sys.executable, "-c", command],
        "timeoutSeconds": 30,
        "report": {"format": "vitest", "path": report},
    }
    if browser:
        lane["browserArtifactGlob"] = "browser/**/*"
    gate["lanes"] = [lane]


def write_python_findings(artifacts: Path, findings: list[JsonValue]) -> None:
    path = artifacts / "scans/python-vulnerability-report.json"
    report = json.loads(path.read_text())
    assert isinstance(report, dict)
    report["findingCount"] = len(findings)
    report["findings"] = findings
    path.write_text(json.dumps(report))


def mutate(name: PoisonName, fixture: PoisonFixture) -> None:
    manifest = fixture.manifest
    plotlot = fixture.plotlot
    artifacts = fixture.artifacts
    match name:
        case "contract-drift":
            binding(manifest, "contract")["sha256"] = "0" * 64
        case "migration-drift":
            binding(manifest, "migration")["sha256"] = "0" * 64
        case "generated-client-drift":
            binding(manifest, "generated-client")["sha256"] = "0" * 64
        case "wrong-sha":
            repositories = manifest["repositories"]
            assert isinstance(repositories, dict)
            repository = repositories["plotlot"]
            assert isinstance(repository, dict)
            repository["head"] = "0" * 40
        case "dirty-dependency":
            (plotlot / "package.json").write_text('{"private":false}\n')
        case "skipped-test":
            set_lane(
                manifest,
                f"from pathlib import Path; Path({str(artifacts / 'reports.json')!r}).write_text("
                f"{json.dumps({'numTotalTests': 1, 'numPendingTests': 1})!r})",
                "reports.json",
            )
        case "zero-test":
            set_lane(
                manifest,
                f"from pathlib import Path; Path({str(artifacts / 'reports.json')!r}).write_text("
                f"{json.dumps({'numTotalTests': 0, 'numPendingTests': 0})!r})",
                "reports.json",
            )
        case "missing-browser-artifact":
            set_lane(
                manifest,
                f"from pathlib import Path; Path({str(artifacts / 'reports.json')!r}).write_text("
                f"{json.dumps({'numTotalTests': 1, 'numPendingTests': 0})!r})",
                "reports.json",
                browser=True,
            )
        case "fixture-live-contamination":
            (artifacts / "scans/content.json").write_text(
                '{"compositionMode":"live","source":"fixture"}\n'
            )
        case "secret-shape":
            (artifacts / "scans/content.json").write_text('{"token":"sk_live_1234567890abcdef"}\n')
        case "pii-raw-licensed-data":
            (artifacts / "scans/content.json").write_text('{"payload":"RAW_LICENSED_DATA"}\n')
        case "sbom-critical-finding":
            write_python_findings(
                artifacts,
                [{"severity": "critical", "dependencyScope": "transitive"}],
            )
        case "sbom-kev-finding":
            write_python_findings(
                artifacts,
                [{"knownExploited": True, "severity": "high"}],
            )
        case "sbom-direct-fixable":
            write_python_findings(
                artifacts,
                [
                    {
                        "knownExploited": False,
                        "severity": "unknown",
                        "dependencyScope": "direct",
                        "nonBreakingFixAvailable": True,
                    }
                ],
            )
        case "sbom-enrichment-stale":
            path = artifacts / "scans/python-vulnerability-report.json"
            report = json.loads(path.read_text())
            assert isinstance(report, dict)
            report["generatedAt"] = "2020-01-01T00:00:00+00:00"
            path.write_text(json.dumps(report))
        case "missing-rollback-metadata":
            (artifacts / "scans/rollback.json").write_text('{"candidateSha":"a"}\n')
        case unreachable:
            assert_never(unreachable)
    sign(manifest)


def run_probe(root: Path, runner: Path, name: PoisonName, expected: str) -> JsonObject:
    probe = root / name
    probe.mkdir()
    plotlot = probe / "plotlot"
    byright = probe / "byright"
    artifacts = probe / "artifacts"
    make_repo(plotlot, "plotlot")
    make_repo(byright, "byright")
    manifest = base_manifest(plotlot, byright, artifacts)
    mutate(
        name,
        PoisonFixture(
            manifest=manifest,
            plotlot=plotlot,
            byright=byright,
            artifacts=artifacts,
        ),
    )
    manifest_path = probe / "repository-pair.json"
    manifest_path.write_text(json.dumps(manifest))
    environment = os.environ.copy()
    environment["PAIR_MANIFEST_SIGNING_KEY"] = KEY
    result = subprocess.run(
        [
            str(runner),
            "--plotlot-clone",
            str(plotlot),
            "--byright-clone",
            str(byright),
            "--manifest",
            str(manifest_path),
            "--full",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    observable = result.stderr.strip()
    return {
        "poison": name,
        "expectedCode": expected,
        "actualExitCode": result.returncode,
        "observable": observable,
        "passed": result.returncode != 0 and f"code={expected}" in observable,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_path", nargs="?")
    parser.add_argument("--output")
    arguments = parser.parse_args()
    if arguments.output_path is not None and arguments.output is not None:
        parser.error("choose either output_path or --output")
    runner = Path(__file__).with_name("verify_repository_pair.sh")
    selected_output = arguments.output or arguments.output_path or "poison-matrix.json"
    output = Path(selected_output).resolve()
    temporary = Path(tempfile.mkdtemp(prefix="repository-pair-poisons-"))
    results: list[JsonValue] = []
    try:
        for name, expected in POISONS.items():
            results.append(run_probe(temporary, runner, name, expected))
        passed = all(isinstance(value, dict) and value.get("passed") is True for value in results)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"passed": passed, "results": results}, indent=2) + "\n")
        return 0 if passed else 1
    finally:
        shutil.rmtree(temporary)


if __name__ == "__main__":
    raise SystemExit(main())
