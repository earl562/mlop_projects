from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pair_gate_types import (
    JsonObject,
    gate_error,
    require_int,
    require_list,
    require_object,
    require_string,
)
from python_vulnerability_enrichment import enrich


def create_python_sbom(
    plotlot: Path,
    output: Path,
    raw_audit_output: Path,
    enrichment_cache: Path,
    vulnerability_report: Path,
) -> None:
    with tempfile.NamedTemporaryFile(suffix=".requirements.txt") as requirements:
        export = subprocess.run(
            [
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--quiet",
                "--output-file",
                requirements.name,
            ],
            cwd=plotlot / "plotlot",
            check=False,
            capture_output=True,
            timeout=180,
        )
        if export.returncode != 0:
            raise gate_error("PAIR_E_MANIFEST", "uv production dependency export failed")
        audit = subprocess.run(
            [
                "uvx",
                "pip-audit",
                "--requirement",
                requirements.name,
                "--disable-pip",
                "--no-deps",
                "--format",
                "cyclonedx-json",
                "--progress-spinner",
                "off",
                "--output",
                str(output),
            ],
            check=False,
            capture_output=True,
            timeout=300,
        )
        raw_audit = subprocess.run(
            [
                "uvx",
                "pip-audit",
                "--requirement",
                requirements.name,
                "--disable-pip",
                "--no-deps",
                "--format",
                "json",
                "--progress-spinner",
                "off",
                "--output",
                str(raw_audit_output),
            ],
            check=False,
            capture_output=True,
            timeout=300,
        )
    if audit.returncode not in {0, 1} or not output.is_file():
        raise gate_error("PAIR_E_MANIFEST", "Python production dependency audit failed")
    if raw_audit.returncode not in {0, 1} or not raw_audit_output.is_file():
        raise gate_error("PAIR_E_MANIFEST", "Python vulnerability inventory failed")
    document = require_object(json.loads(output.read_text()), "Python CycloneDX SBOM")
    if document.get("bomFormat") != "CycloneDX":
        raise gate_error("PAIR_E_MANIFEST", "Python audit did not emit CycloneDX")
    for raw_vulnerability in require_list(
        document.get("vulnerabilities"), "Python vulnerabilities"
    ):
        require_object(raw_vulnerability, "Python vulnerability").pop("description", None)
    output.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    enrich(plotlot, raw_audit_output, enrichment_cache, vulnerability_report)
    raw_document = require_object(json.loads(raw_audit_output.read_text()), "pip-audit JSON")
    for raw_dependency in require_list(raw_document.get("dependencies"), "audit dependencies"):
        dependency = require_object(raw_dependency, "audit dependency")
        for raw_vulnerability in require_list(
            dependency.get("vulns", []), "audit vulnerabilities"
        ):
            require_object(raw_vulnerability, "audit vulnerability").pop("description", None)
    raw_audit_output.write_bytes(
        json.dumps(raw_document, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )


def verify_python_supply_chain(artifact_root: Path, gate: JsonObject) -> None:
    sbom_path = artifact_root / require_string(
        gate.get("pythonSbomPath"), "releaseGate.pythonSbomPath"
    )
    sbom = require_object(json.loads(sbom_path.read_text()), "Python SBOM")
    components = [
        require_object(value, "Python component")
        for value in require_list(sbom.get("components"), "Python components")
    ]
    names = {require_string(component.get("name"), "Python component name") for component in components}
    required = {
        require_string(value, "required Python component")
        for value in require_list(
            gate.get("requiredPythonComponents"), "releaseGate.requiredPythonComponents"
        )
    }
    if not required.issubset(names):
        raise gate_error("PAIR_E_SBOM_CRITICAL", "required Python component missing from SBOM")
    for raw_vulnerability in require_list(sbom.get("vulnerabilities"), "Python vulnerabilities"):
        vulnerability = require_object(raw_vulnerability, "Python vulnerability")
        for raw_rating in require_list(vulnerability.get("ratings", []), "vulnerability ratings"):
            rating = require_object(raw_rating, "vulnerability rating")
            if str(rating.get("severity", "")).lower() == "critical":
                raise gate_error("PAIR_E_SBOM_CRITICAL", "critical Python SBOM finding")
    licenses_path = artifact_root / require_string(
        gate.get("pythonLicensesPath"), "releaseGate.pythonLicensesPath"
    )
    licenses = require_object(json.loads(licenses_path.read_text()), "Python licenses")
    entries = [
        require_object(value, "Python license")
        for value in require_list(licenses.get("packages"), "Python license packages")
    ]
    licensed = {
        require_string(entry.get("name"), "licensed package name").lower()
        for entry in entries
        if isinstance(entry.get("license"), str) and entry.get("license")
    }
    if not {name.lower() for name in required}.issubset(licensed):
        raise gate_error("PAIR_E_SBOM_CRITICAL", "required Python component license is missing")
    cache_path = artifact_root / require_string(
        gate.get("pythonEnrichmentCachePath"), "releaseGate.pythonEnrichmentCachePath"
    )
    report_path = artifact_root / require_string(
        gate.get("pythonVulnerabilityReportPath"),
        "releaseGate.pythonVulnerabilityReportPath",
    )
    report = require_object(json.loads(report_path.read_text()), "Python vulnerability report")
    if report.get("enrichmentStatus") != "available":
        raise gate_error("PAIR_E_SBOM_ENRICHMENT", "Python enrichment is unavailable")
    expected_hash = require_string(report.get("cacheSha256"), "enrichment cache hash")
    if hashlib.sha256(cache_path.read_bytes()).hexdigest() != expected_hash:
        raise gate_error("PAIR_E_SBOM_ENRICHMENT", "Python enrichment cache hash mismatch")
    generated = datetime.fromisoformat(
        require_string(report.get("generatedAt"), "enrichment generatedAt")
    )
    if generated.tzinfo is None:
        raise gate_error("PAIR_E_SBOM_ENRICHMENT", "enrichment timestamp is not timezone-aware")
    age = datetime.now(timezone.utc) - generated
    if age < timedelta(minutes=-5) or age > timedelta(
        hours=require_int(report.get("maxAgeHours"), "enrichment maxAgeHours")
    ):
        raise gate_error("PAIR_E_SBOM_ENRICHMENT", "Python enrichment is stale")
    for raw_finding in require_list(report.get("findings"), "Python normalized findings"):
        finding = require_object(raw_finding, "Python normalized finding")
        if finding.get("knownExploited") is True:
            raise gate_error("PAIR_E_SBOM_KEV", "Python finding is CISA KEV-listed")
        if str(finding.get("severity", "")).lower() == "critical":
            raise gate_error("PAIR_E_SBOM_CRITICAL", "critical normalized Python finding")
        if (
            finding.get("dependencyScope") == "direct"
            and finding.get("nonBreakingFixAvailable") is True
        ):
            raise gate_error(
                "PAIR_E_SBOM_DIRECT_FIXABLE",
                "direct production dependency has an available non-breaking fix",
            )
        if (
            finding.get("dependencyScope") == "transitive"
            and finding.get("severity") == "unknown"
        ):
            disposition = require_object(
                finding.get("riskDisposition"), "unscored transitive risk disposition"
            )
            for field in ("owner", "rationale", "recheckAt", "expiresAt"):
                require_string(disposition.get(field), f"riskDisposition.{field}")
            expiry = datetime.fromisoformat(
                require_string(disposition.get("expiresAt"), "riskDisposition.expiresAt")
            )
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise gate_error(
                    "PAIR_E_SBOM_ENRICHMENT",
                    "unscored transitive risk disposition is expired",
                )
