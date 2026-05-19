#!/usr/bin/env python3
"""Push a feature branch and open or reuse a draft PR into main."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ALLOWED_BRANCH_PREFIXES = ("codex/", "dev/", "feat/", "fix/", "hotfix/")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run(cmd: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        check=check,
        text=True,
        capture_output=True,
    )


def current_branch(root: Path) -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root).stdout.strip()


def tracked_changes_present(status_output: str) -> bool:
    return any(line.strip() for line in status_output.splitlines())


def validate_branch_name(branch: str) -> None:
    if branch == "main":
        raise ValueError("Refusing to ship from main. Create or switch to a codex/dev/feat/fix/hotfix branch.")
    if branch == "HEAD":
        raise ValueError("Detached HEAD is not a shippable branch. Check out a named branch first.")
    if not any(branch.startswith(prefix) for prefix in ALLOWED_BRANCH_PREFIXES):
        raise ValueError(
            f"Branch {branch!r} does not use an approved delivery prefix {ALLOWED_BRANCH_PREFIXES}."
        )


def build_pr_body(branch: str, base: str) -> str:
    return "\n".join(
        [
            "## Promotion Summary",
            "",
            f"This draft PR promotes `{branch}` into `{base}` after passing the canonical local checks.",
            "",
            "## Promotion Checklist",
            "",
            "- [ ] `make deploy-doctor` is clean",
            "- [ ] `make verify-local` is clean",
            "- [ ] Branch CI is green",
            "- [ ] Required review/approval is complete",
            "- [ ] Merge to `main` only after approval",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="main", help="Base branch for the promotion PR (default: main)")
    parser.add_argument("--skip-doctor", action="store_true", help="Skip deploy-doctor before pushing")
    parser.add_argument("--skip-verify", action="store_true", help="Skip verify-local before pushing")
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="When verifying locally, skip Playwright browser lanes.",
    )
    args = parser.parse_args()

    root = repo_root()
    branch = current_branch(root)
    validate_branch_name(branch)

    status = run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=root,
    ).stdout
    if tracked_changes_present(status):
        raise SystemExit(
            "Tracked changes are still present. Commit or stash them before running ship-branch."
        )

    run(["git", "fetch", "origin"], cwd=root)

    if not args.skip_doctor:
        doctor_cmd = [sys.executable, str(root / "plotlot" / "scripts" / "deploy_doctor.py"), "--fix-local-links"]
        doctor = subprocess.run(doctor_cmd, cwd=str(root), text=True)
        if doctor.returncode != 0:
            raise SystemExit("deploy-doctor reported blocking errors. Fix them before shipping the branch.")

    if not args.skip_verify:
        verify_cmd = ["bash", str(root / "plotlot" / "scripts" / "verify_local_success.sh")]
        if args.skip_browser:
            verify_cmd.append("--skip-browser")
        verify = subprocess.run(verify_cmd, cwd=str(root / "plotlot"), text=True)
        if verify.returncode != 0:
            raise SystemExit("verify_local_success.sh failed. Fix the branch before shipping it.")

    push = subprocess.run(["git", "push", "-u", "origin", branch], cwd=str(root), text=True)
    if push.returncode != 0:
        raise SystemExit(push.returncode)

    pr_list = run(
        [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--base",
            args.base,
            "--json",
            "number,url,isDraft,state",
        ],
        cwd=root,
    )
    prs = json.loads(pr_list.stdout)
    if prs:
        print(f"Reused PR #{prs[0]['number']}: {prs[0]['url']}")
        return 0

    title = f"[Promote] {branch} -> {args.base}"
    body = build_pr_body(branch, args.base)
    create = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--draft",
            "--base",
            args.base,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=str(root),
        text=True,
    )
    if create.returncode != 0:
        raise SystemExit(create.returncode)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
