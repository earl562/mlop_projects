#!/usr/bin/env python3
"""Check local and platform deployment settings against the canonical PlotLot layout."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

EXPECTED_RENDER_ROOT = "plotlot"
EXPECTED_RENDER_DOCKERFILE = "./Dockerfile"
EXPECTED_RENDER_DOCKER_CONTEXT = "."
EXPECTED_RENDER_HEALTH = "/health"
EXPECTED_VERCEL_PROJECT = "plotlot-v2"
EXPECTED_VERCEL_ROOT = "plotlot/frontend"
ROOT_NODE_MANIFESTS = ("package.json", "package-lock.json")
STALE_VERCEL_LINK_DIRS = (
    Path("frontend/.vercel"),
    Path("apps/plotlot/frontend/.vercel"),
)
CANONICAL_VERCEL_PROJECT_FILES = (
    Path(".vercel/project.json"),
    Path("plotlot/frontend/.vercel/project.json"),
)
RENDER_SERVICE_NAME = "plotlot-api"
ALLOWED_BRANCH_PREFIXES = ("codex/", "dev/", "feat/", "fix/", "hotfix/")


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_capture(cmd: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def inspect_root_node_manifests(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for rel in ROOT_NODE_MANIFESTS:
        if (root / rel).exists():
            findings.append(
                Finding(
                    "error",
                    "non_canonical_root_node_manifest",
                    f"Root-level Node manifest {rel} exists; keep package files under plotlot/frontend/ only.",
                )
            )
    return findings


def inspect_local_vercel_links(root: Path) -> list[Finding]:
    findings: list[Finding] = []

    for rel in STALE_VERCEL_LINK_DIRS:
        if (root / rel).exists():
            findings.append(
                Finding(
                    "error",
                    "stale_vercel_link",
                    f"Stale local Vercel link directory exists at {rel.as_posix()}; it can route CLI commands to the wrong project root.",
                )
            )

    for rel in CANONICAL_VERCEL_PROJECT_FILES:
        data = load_json(root / rel)
        if data is None:
            continue

        settings = data.get("settings", {})
        project_name = data.get("projectName")
        root_directory = settings.get("rootDirectory")

        if project_name != EXPECTED_VERCEL_PROJECT:
            findings.append(
                Finding(
                    "error",
                    "vercel_project_mismatch",
                    f"{rel.as_posix()} points at project {project_name!r}; expected {EXPECTED_VERCEL_PROJECT!r}.",
                )
            )
        if root_directory != EXPECTED_VERCEL_ROOT:
            findings.append(
                Finding(
                    "error",
                    "vercel_root_mismatch",
                    f"{rel.as_posix()} uses rootDirectory {root_directory!r}; expected {EXPECTED_VERCEL_ROOT!r}.",
                )
            )

    return findings


def normalize_render_service(record: dict) -> dict:
    return record.get("service", record)


def parse_render_cli_api_key() -> str | None:
    config_path = Path.home() / ".render" / "cli.yaml"
    if not config_path.exists():
        return None

    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("key:"):
            return line.split(":", 1)[1].strip()
    return None


def database_identity(raw_url: str | None) -> tuple[str | None, str | None]:
    if not raw_url:
        return (None, None)

    normalized = raw_url
    if normalized.startswith("postgresql+asyncpg://"):
        normalized = normalized.replace("postgresql+asyncpg://", "postgresql://", 1)
    elif normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql://", 1)

    parsed = urlparse(normalized)
    host = parsed.hostname
    database = parsed.path.lstrip("/") or None
    return (host, database)


def inspect_render_env_var_drift(env_vars: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    database_url = env_vars.get("DATABASE_URL")
    mlflow_url = env_vars.get("MLFLOW_TRACKING_URI")

    db_host, db_name = database_identity(database_url)
    mlflow_host, mlflow_name = database_identity(mlflow_url)

    if database_url and mlflow_url and db_host and db_name and (db_host, db_name) == (mlflow_host, mlflow_name):
        findings.append(
            Finding(
                "warning",
                "render_shared_mlflow_database",
                "Render MLFLOW_TRACKING_URI points at the same database as DATABASE_URL; keep MLflow on a dedicated tracking DB or local sqlite to avoid schema/version conflicts. See plotlot/docs/runbooks/render-mlflow-tracking.md.",
            )
        )

    return findings


def inspect_render_service(service: dict) -> list[Finding]:
    findings: list[Finding] = []
    service = normalize_render_service(service)
    details = service.get("serviceDetails", {})
    env_details = details.get("envSpecificDetails", {})

    if service.get("rootDir") != EXPECTED_RENDER_ROOT:
        findings.append(
            Finding(
                "error",
                "render_root_mismatch",
                f"Render service {service.get('name')!r} uses rootDir {service.get('rootDir')!r}; expected {EXPECTED_RENDER_ROOT!r}.",
            )
        )
    if env_details.get("dockerfilePath") != EXPECTED_RENDER_DOCKERFILE:
        findings.append(
            Finding(
                "error",
                "render_dockerfile_mismatch",
                f"Render dockerfilePath is {env_details.get('dockerfilePath')!r}; expected {EXPECTED_RENDER_DOCKERFILE!r}.",
            )
        )
    if env_details.get("dockerContext") != EXPECTED_RENDER_DOCKER_CONTEXT:
        findings.append(
            Finding(
                "error",
                "render_docker_context_mismatch",
                f"Render dockerContext is {env_details.get('dockerContext')!r}; expected {EXPECTED_RENDER_DOCKER_CONTEXT!r}.",
            )
        )
    if details.get("healthCheckPath") != EXPECTED_RENDER_HEALTH:
        findings.append(
            Finding(
                "error",
                "render_health_mismatch",
                f"Render healthCheckPath is {details.get('healthCheckPath')!r}; expected {EXPECTED_RENDER_HEALTH!r}.",
            )
        )

    return findings


def fetch_render_service(service_name: str) -> tuple[dict | None, Finding | None]:
    try:
        output = run_capture(["render", "services", "-o", "json"])
    except FileNotFoundError:
        return None, Finding(
            "warning",
            "render_cli_missing",
            "Render CLI is not installed; skipping live Render service inspection.",
        )
    except subprocess.CalledProcessError as exc:
        return None, Finding(
            "warning",
            "render_cli_unavailable",
            f"Render CLI could not list services: {exc.stderr.strip() or exc.stdout.strip() or exc}",
        )

    services = json.loads(output)
    for record in services:
        service = normalize_render_service(record)
        if service.get("name") == service_name:
            return record, None

    return None, Finding(
        "warning",
        "render_service_missing",
        f"Could not find a Render service named {service_name!r} in the active workspace.",
    )


def fetch_render_env_vars(service_id: str) -> tuple[dict[str, str] | None, Finding | None]:
    api_key = parse_render_cli_api_key()
    if not api_key:
        return None, Finding(
            "warning",
            "render_cli_key_missing",
            "Render CLI API key is unavailable; skipping live Render env-var inspection.",
        )

    cmd = [
        "python3",
        "-c",
        (
            "import json, sys, urllib.request; "
            "service_id, api_key = sys.argv[1], sys.argv[2]; "
            "req = urllib.request.Request("
            "f'https://api.render.com/v1/services/{service_id}/env-vars', "
            "headers={'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'}"
            "); "
            "data = json.load(urllib.request.urlopen(req, timeout=20)); "
            "print(json.dumps({item['envVar']['key']: item['envVar']['value'] for item in data}))"
        ),
        service_id,
        api_key,
    ]
    try:
        output = run_capture(cmd)
    except subprocess.CalledProcessError as exc:
        return None, Finding(
            "warning",
            "render_env_fetch_failed",
            f"Render env-var inspection failed: {exc.stderr.strip() or exc.stdout.strip() or exc}",
        )

    return json.loads(output), None


def current_branch(root: Path) -> str:
    return run_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root).strip()


def inspect_branch(root: Path) -> list[Finding]:
    branch = current_branch(root)
    if branch == "main":
        return [
            Finding(
                "warning",
                "main_branch_active",
                "Current branch is main; use a codex/dev/feat/fix/hotfix branch for day-to-day shipping work.",
            )
        ]
    if branch != "HEAD" and not any(branch.startswith(prefix) for prefix in ALLOWED_BRANCH_PREFIXES):
        return [
            Finding(
                "warning",
                "nonstandard_branch_prefix",
                f"Current branch {branch!r} does not use a standard delivery prefix {ALLOWED_BRANCH_PREFIXES}.",
            )
        ]
    return []


def remove_stale_vercel_links(root: Path) -> list[str]:
    removed: list[str] = []
    for rel in STALE_VERCEL_LINK_DIRS:
        target = root / rel
        if target.exists():
            shutil.rmtree(target)
            removed.append(rel.as_posix())
    return removed


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "Deployment doctor passed."

    lines: list[str] = []
    for finding in findings:
        prefix = "ERROR" if finding.level == "error" else "WARN"
        lines.append(f"[{prefix}] {finding.message}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix-local-links",
        action="store_true",
        help="Delete stale non-canonical local .vercel link directories before checking.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()

    removed: list[str] = []
    if args.fix_local_links:
        removed = remove_stale_vercel_links(root)

    findings: list[Finding] = []
    findings.extend(inspect_root_node_manifests(root))
    findings.extend(inspect_local_vercel_links(root))
    findings.extend(inspect_branch(root))

    render_service, render_warning = fetch_render_service(RENDER_SERVICE_NAME)
    if render_warning is not None:
        findings.append(render_warning)
    elif render_service is not None:
        findings.extend(inspect_render_service(render_service))
        service = normalize_render_service(render_service)
        env_vars, env_warning = fetch_render_env_vars(service["id"])
        if env_warning is not None:
            findings.append(env_warning)
        elif env_vars is not None:
            findings.extend(inspect_render_env_var_drift(env_vars))

    if removed:
        print("Removed stale local Vercel link directories:")
        for rel in removed:
            print(f"- {rel}")

    print(format_findings(findings))
    return 1 if any(f.level == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
