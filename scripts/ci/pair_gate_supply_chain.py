from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from pair_gate_types import (
    JsonObject,
    gate_error,
    require_list,
    require_object,
    require_string,
)


def create_python_sbom(plotlot: Path, output: Path) -> None:
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
    if audit.returncode not in {0, 1} or not output.is_file():
        raise gate_error("PAIR_E_MANIFEST", "Python production dependency audit failed")
    document = require_object(json.loads(output.read_text()), "Python CycloneDX SBOM")
    if document.get("bomFormat") != "CycloneDX":
        raise gate_error("PAIR_E_MANIFEST", "Python audit did not emit CycloneDX")
    for raw_vulnerability in require_list(
        document.get("vulnerabilities"), "Python vulnerabilities"
    ):
        require_object(raw_vulnerability, "Python vulnerability").pop("description", None)
    output.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")


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
