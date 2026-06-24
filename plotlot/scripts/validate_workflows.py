#!/usr/bin/env python3
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REQUIRED_ACTION_REFS: Final[Mapping[str, str]] = {
    "actions/checkout": "v7",
    "actions/github-script": "v9",
    "actions/setup-node": "v6",
    "actions/upload-artifact": "v7",
}
REQUIRED_CHECKOUT_REF: Final = REQUIRED_ACTION_REFS["actions/checkout"]
UNSTABLE_ACTION_REFS: Final = {"latest", "main", "master"}
JOB_HEADER_PREFIX_SPACES: Final = 2
FRONTEND_NO_DB_E2E_REQUIRED_SPECS: Final = (
    ("tests/lookup-release-gate.no-db.spec.ts", "missing-lookup-release-gate-e2e"),
    ("tests/agent-run-panel.no-db.spec.ts", "missing-agent-run-panel-e2e"),
)
CI_REQUIRED_COMMANDS: Final = (
    ("python3 plotlot/scripts/check_repo_hygiene.py", "missing-ci-repo-hygiene"),
    ("python3 plotlot/scripts/validate_workflows.py", "missing-ci-workflow-policy"),
    ("uv run python -m pytest tests/unit/", "missing-ci-backend-unit"),
    ("tests/eval/test_agentic_land_use_goldset.py", "missing-ci-lookup-agentic-goldset"),
    ("npm run build", "missing-ci-frontend-build"),
    ("npm run test:e2e:no-db", "missing-ci-playwright-no-db"),
    ("npm run test:e2e:db", "missing-ci-playwright-db"),
)


@dataclass(frozen=True, slots=True)
class WorkflowPolicyViolation:
    workflow: str
    location: str
    reason: str


def _violation(workflow: str, location: str, reason: str) -> WorkflowPolicyViolation:
    return WorkflowPolicyViolation(workflow=workflow, location=location, reason=reason)


def validate_workflow_text(workflow: str, text: str) -> list[WorkflowPolicyViolation]:
    lines = text.splitlines()
    violations: list[WorkflowPolicyViolation] = []
    violations.extend(_validate_action_refs(workflow, lines))
    violations.extend(_validate_container_images(workflow, lines))
    violations.extend(_validate_job_timeouts(workflow, lines))
    violations.extend(_validate_job_permissions(workflow, lines))
    violations.extend(_validate_triggers(workflow, lines))
    return violations


def _validate_action_refs(workflow: str, lines: list[str]) -> list[WorkflowPolicyViolation]:
    violations: list[WorkflowPolicyViolation] = []
    for index, line in enumerate(lines, start=1):
        action = _uses_value(line)
        if action is None:
            continue

        ref = _action_ref(action)
        if ref is None or ref in UNSTABLE_ACTION_REFS:
            violations.append(_violation(workflow, f"line {index}", "unstable-action-ref"))

        action_name = _action_name(action)
        required_ref = REQUIRED_ACTION_REFS.get(action_name)
        if required_ref is not None and ref != required_ref:
            violations.append(
                _violation(
                    workflow,
                    f"line {index}",
                    _action_version_violation_reason(action_name),
                )
            )

        if action_name != "actions/checkout":
            continue

        if not _step_sets_checkout_credentials_false(lines, index - 1):
            violations.append(
                _violation(
                    workflow,
                    f"line {index}",
                    "checkout-persist-credentials-not-disabled",
                )
            )

    return violations


def _validate_container_images(workflow: str, lines: list[str]) -> list[WorkflowPolicyViolation]:
    violations: list[WorkflowPolicyViolation] = []
    for index, line in enumerate(lines, start=1):
        image = _image_value(line)
        if image is None:
            continue
        if "@sha256:" in image:
            continue
        violations.append(_violation(workflow, f"line {index}", "service-image-not-digest-pinned"))
    return violations


def _validate_job_timeouts(workflow: str, lines: list[str]) -> list[WorkflowPolicyViolation]:
    violations: list[WorkflowPolicyViolation] = []
    for job_name, job_lines in _job_blocks(lines):
        if not _block_has_key(job_lines, "runs-on:"):
            continue
        if _block_has_key(job_lines, "timeout-minutes:"):
            continue
        violations.append(_violation(workflow, f"job {job_name}", "missing-job-timeout"))
    return violations


def _validate_job_permissions(workflow: str, lines: list[str]) -> list[WorkflowPolicyViolation]:
    violations: list[WorkflowPolicyViolation] = []
    for job_name, job_lines in _job_blocks(lines):
        if not _block_has_key(job_lines, "runs-on:"):
            continue
        if _block_has_key(job_lines, "permissions:"):
            continue
        violations.append(_violation(workflow, f"job {job_name}", "missing-job-permissions"))
    return violations


def _validate_triggers(workflow: str, lines: list[str]) -> list[WorkflowPolicyViolation]:
    violations: list[WorkflowPolicyViolation] = []
    for index, line in enumerate(lines, start=1):
        if line.strip().startswith("pull_request_target:"):
            violations.append(_violation(workflow, f"line {index}", "pull-request-target-trigger"))
    return violations


def _uses_value(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("- uses:"):
        return stripped.removeprefix("- uses:").strip().strip("\"'")
    if stripped.startswith("uses:"):
        return stripped.removeprefix("uses:").strip().strip("\"'")
    return None


def _image_value(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("image:"):
        return None
    return stripped.removeprefix("image:").strip().strip("\"'")


def _action_name(action: str) -> str:
    return action.rsplit("@", maxsplit=1)[0]


def _action_ref(action: str) -> str | None:
    parts = action.rsplit("@", maxsplit=1)
    if len(parts) != 2:
        return None
    return parts[1]


def _action_version_violation_reason(action_name: str) -> str:
    if action_name == "actions/checkout":
        return "checkout-action-version"
    return "official-action-version"


def _step_sets_checkout_credentials_false(lines: list[str], start_index: int) -> bool:
    for line in _step_block(lines, start_index):
        if line.strip() == "persist-credentials: false":
            return True
    return False


def _step_block(lines: list[str], start_index: int) -> list[str]:
    first_line = lines[start_index]
    step_indent = len(first_line) - len(first_line.lstrip())
    block: list[str] = [first_line]
    for line in lines[start_index + 1 :]:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("- ") and indent <= step_indent:
            break
        block.append(line)
    return block


def _job_blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    current_name = ""
    current_lines: list[str] = []
    in_jobs = False
    for line in lines:
        if line.startswith("jobs:"):
            in_jobs = True
            continue
        if not in_jobs:
            continue

        job_name = _job_name(line)
        if job_name is not None:
            if current_name:
                blocks.append((current_name, current_lines))
            current_name = job_name
            current_lines = [line]
            continue

        if current_name:
            current_lines.append(line)

    if current_name:
        blocks.append((current_name, current_lines))
    return blocks


def _job_name(line: str) -> str | None:
    indent = len(line) - len(line.lstrip())
    stripped = line.strip()
    if indent != JOB_HEADER_PREFIX_SPACES:
        return None
    if not stripped.endswith(":"):
        return None
    if stripped.startswith("-"):
        return None
    return stripped.removesuffix(":")


def _block_has_key(lines: list[str], key: str) -> bool:
    return any(line.strip().startswith(key) for line in lines)


def workflow_files(repo_root: Path) -> list[Path]:
    return sorted((repo_root / ".github" / "workflows").glob("*.yml"))


def validate_required_frontend_scripts(
    repo_root: Path,
    scripts: Mapping[str, str] | None = None,
) -> list[WorkflowPolicyViolation]:
    frontend_scripts = scripts if scripts is not None else _frontend_package_scripts(repo_root)
    command = frontend_scripts.get("test:e2e:no-db", "")
    violations: list[WorkflowPolicyViolation] = []
    for spec_path, reason in FRONTEND_NO_DB_E2E_REQUIRED_SPECS:
        if spec_path in command:
            continue
        violations.append(_violation("frontend/package.json", "scripts.test:e2e:no-db", reason))
    return violations


def validate_required_ci_workflow_text(text: str) -> list[WorkflowPolicyViolation]:
    violations: list[WorkflowPolicyViolation] = []
    for command, reason in CI_REQUIRED_COMMANDS:
        if command in text:
            continue
        violations.append(_violation(".github/workflows/ci.yml", "required commands", reason))
    return violations


def validate_workflows(repo_root: Path) -> list[WorkflowPolicyViolation]:
    violations: list[WorkflowPolicyViolation] = []
    for workflow_path in workflow_files(repo_root):
        violations.extend(
            validate_workflow_text(
                workflow_path.relative_to(repo_root).as_posix(),
                workflow_path.read_text(encoding="utf-8"),
            )
        )
    return violations


def validate_ci_policy(repo_root: Path) -> list[WorkflowPolicyViolation]:
    violations = validate_workflows(repo_root)
    violations.extend(validate_required_frontend_scripts(repo_root))
    violations.extend(
        validate_required_ci_workflow_text(
            (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        )
    )
    return violations


def _frontend_package_scripts(repo_root: Path) -> dict[str, str]:
    package_json = repo_root / "plotlot" / "frontend" / "package.json"
    payload = json.loads(package_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {
        key: value
        for key, value in scripts.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def main() -> int:
    repo_root: Final = Path(__file__).resolve().parents[2]
    violations = validate_ci_policy(repo_root)
    if not violations:
        print("Workflow policy check passed.")
        return 0

    print("Workflow policy check failed.")
    for violation in violations:
        print(f"- {violation.workflow}:{violation.location} [{violation.reason}]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
