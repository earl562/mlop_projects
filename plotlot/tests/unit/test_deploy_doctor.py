"""Unit tests for deployment doctor checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_deploy_doctor_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "deploy_doctor.py"
    spec = importlib.util.spec_from_file_location("plotlot_deploy_doctor", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


deploy_doctor = _load_deploy_doctor_module()


def test_inspect_root_node_manifests_flags_root_package_files(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    findings = deploy_doctor.inspect_root_node_manifests(tmp_path)

    assert [finding.code for finding in findings] == [
        "non_canonical_root_node_manifest",
        "non_canonical_root_node_manifest",
    ]


def test_inspect_local_vercel_links_flags_stale_and_misaligned_links(tmp_path: Path):
    stale = tmp_path / "frontend" / ".vercel"
    stale.mkdir(parents=True)
    (stale / "project.json").write_text("{}", encoding="utf-8")

    canonical = tmp_path / ".vercel"
    canonical.mkdir(parents=True)
    (canonical / "project.json").write_text(
        '{"projectName":"wrong-project","settings":{"rootDirectory":"frontend"}}',
        encoding="utf-8",
    )

    findings = deploy_doctor.inspect_local_vercel_links(tmp_path)
    codes = [finding.code for finding in findings]

    assert "stale_vercel_link" in codes
    assert "vercel_project_mismatch" in codes
    assert "vercel_root_mismatch" in codes


def test_inspect_render_service_flags_root_and_health_mismatch():
    findings = deploy_doctor.inspect_render_service(
        {
            "service": {
                "name": "plotlot-api",
                "rootDir": "apps/plotlot",
                "serviceDetails": {
                    "healthCheckPath": "",
                    "envSpecificDetails": {
                        "dockerfilePath": "./plotlot/Dockerfile",
                        "dockerContext": "./plotlot",
                    },
                },
            }
        }
    )
    codes = [finding.code for finding in findings]

    assert "render_root_mismatch" in codes
    assert "render_dockerfile_mismatch" in codes
    assert "render_docker_context_mismatch" in codes
    assert "render_health_mismatch" in codes


def test_remove_stale_vercel_links_deletes_only_known_paths(tmp_path: Path):
    stale = tmp_path / "frontend" / ".vercel"
    stale.mkdir(parents=True)
    keep = tmp_path / ".vercel"
    keep.mkdir(parents=True)

    removed = deploy_doctor.remove_stale_vercel_links(tmp_path)

    assert removed == ["frontend/.vercel"]
    assert not stale.exists()
    assert keep.exists()
