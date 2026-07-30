#!/usr/bin/env python3
"""Report PlotLot credential readiness without printing secret values."""

from __future__ import annotations

import argparse
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PLACEHOLDER_FRAGMENTS = ("your_", "_here", "changeme", "example", "placeholder")


@dataclass(frozen=True)
class RequirementGroup:
    name: str
    purpose: str
    required_any: tuple[str, ...] = ()
    required_all: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    notes: str = ""


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = raw_value.strip()
        try:
            value = shlex.split(value, comments=False, posix=True)[0] if value else ""
        except ValueError:
            value = value.strip('"\'')
        values[key] = value
    return values


def merged_env(env_file: Path) -> dict[str, str]:
    values = parse_env_file(env_file)
    values.update(os.environ)
    return values


def has_value(values: dict[str, str], key: str) -> bool:
    value = values.get(key, "").strip()
    if not value:
        return False
    lowered = value.lower()
    return not any(fragment in lowered for fragment in PLACEHOLDER_FRAGMENTS)


def is_truthy(values: dict[str, str], key: str) -> bool:
    return values.get(key, "").strip().lower() in {"1", "true", "yes", "on"}


def codex_oauth_ready(values: dict[str, str]) -> bool:
    if not is_truthy(values, "PLOTLOT_USE_CODEX_OAUTH"):
        return False
    auth_file = values.get("PLOTLOT_CODEX_AUTH_FILE", "~/.codex/auth.json").strip() or "~/.codex/auth.json"
    return Path(auth_file).expanduser().exists()


def group_status(group: RequirementGroup, values: dict[str, str]) -> dict[str, object]:
    present_all = [key for key in group.required_all if has_value(values, key)]
    missing_all = [key for key in group.required_all if not has_value(values, key)]
    present_any = [key for key in group.required_any if has_value(values, key)]
    optional_present = [key for key in group.optional if has_value(values, key)]
    optional_missing = [key for key in group.optional if not has_value(values, key)]

    ready = not missing_all and (not group.required_any or bool(present_any))
    if group.name == "llm_agent" and codex_oauth_ready(values):
        ready = True
        present_any = [*present_any, "PLOTLOT_USE_CODEX_OAUTH + PLOTLOT_CODEX_AUTH_FILE"]

    missing_any = [] if present_any or not group.required_any else list(group.required_any)
    blocked_by = [*missing_all, *missing_any]

    return {
        "name": group.name,
        "ready": ready,
        "purpose": group.purpose,
        "present": [*present_all, *present_any],
        "missing": blocked_by,
        "optional_present": optional_present,
        "optional_missing": optional_missing,
        "notes": group.notes,
    }


def requirement_groups(values: dict[str, str]) -> list[RequirementGroup]:
    auth_enabled = is_truthy(values, "AUTH_ENABLED")
    clerk_required = ("CLERK_JWKS_URL",) if auth_enabled else ()

    return [
        RequirementGroup(
            name="deterministic_local",
            purpose="Default unit/lint/type/build gates; no external secrets required.",
            notes="Use: bash scripts/verify_local_success.sh",
        ),
        RequirementGroup(
            name="database_backed_e2e",
            purpose="Frontend DB-backed Playwright lanes and backend API smoke tests.",
            required_all=("DATABASE_URL",),
            notes="Also requires a reachable local or remote Postgres instance; use `make db-up` for local Docker DB.",
        ),
        RequirementGroup(
            name="llm_agent",
            purpose="Live agent chat, LLM extraction fallback, and live eval tests.",
            required_any=(
                "OPENROUTER_API_KEY",
                "DEEPSEEK_API_KEY",
                "OPENAI_API_KEY",
                "OPENAI_ACCESS_TOKEN",
                "NVIDIA_API_KEY",
                "GROQ_API_KEY",
                "ANTHROPIC_API_KEY",
            ),
            optional=(
                "PLOTLOT_LLM_PROVIDER",
                "OPENROUTER_BASE_URL",
                "OPENROUTER_MODEL",
                "OPENAI_BASE_URL",
                "OPENAI_MODEL",
                "OPENAI_ORGANIZATION",
                "OPENAI_PROJECT",
                "OPENAI_OAUTH_CLIENT_ID",
            ),
            notes="Codex OAuth also counts when PLOTLOT_USE_CODEX_OAUTH=1 and PLOTLOT_CODEX_AUTH_FILE exists.",
        ),
        RequirementGroup(
            name="geocoding",
            purpose="Live Geocodio address-to-coordinate lookup.",
            required_all=("GEOCODIO_API_KEY",),
        ),
        RequirementGroup(
            name="web_search",
            purpose="Agent web-search/live source lookup via Jina.",
            required_all=("JINA_API_KEY",),
        ),
        RequirementGroup(
            name="stripe_billing",
            purpose="Checkout route and webhook verification.",
            required_all=("STRIPE_SECRET_KEY", "STRIPE_PRO_PRICE_ID", "STRIPE_WEBHOOK_SECRET"),
        ),
        RequirementGroup(
            name="clerk_auth",
            purpose="Authenticated app sessions and backend JWT verification.",
            required_all=clerk_required,
            optional=("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "CLERK_SECRET_KEY"),
            notes="Backend JWKS is required only when AUTH_ENABLED=true; frontend Clerk keys are needed for real sign-in flows.",
        ),
        RequirementGroup(
            name="fal_video",
            purpose="Video generation API route.",
            required_all=("FAL_KEY",),
        ),
        RequirementGroup(
            name="huggingface_embeddings",
            purpose="Hugging Face inference-backed embeddings if that provider path is used.",
            required_all=("HF_TOKEN",),
        ),
        RequirementGroup(
            name="observability",
            purpose="Error and experiment tracking.",
            optional=("SENTRY_DSN", "MLFLOW_TRACKING_URI", "MLFLOW_EXPERIMENT_NAME"),
            notes="Local deterministic tests override MLflow to file:///tmp/plotlot-mlruns.",
        ),
    ]


def render_text(results: Iterable[dict[str, object]], env_file: Path) -> None:
    print(f"Auth readiness source: {env_file}")
    for item in results:
        status = "READY" if item["ready"] else "BLOCKED"
        print(f"\n[{status}] {item['name']}")
        print(f"  Purpose: {item['purpose']}")
        present = item.get("present") or []
        missing = item.get("missing") or []
        if present:
            print("  Present: " + ", ".join(str(key) for key in present))
        if missing:
            print("  Missing: " + ", ".join(str(key) for key in missing))
        optional_present = item.get("optional_present") or []
        optional_missing = item.get("optional_missing") or []
        if optional_present:
            print("  Optional present: " + ", ".join(str(key) for key in optional_present))
        if optional_missing:
            print("  Optional missing: " + ", ".join(str(key) for key in optional_missing))
        if item.get("notes"):
            print(f"  Notes: {item['notes']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env", help="Env file to inspect without printing values")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any credential-backed group is blocked",
    )
    args = parser.parse_args()

    env_file = Path(args.env_file)
    values = merged_env(env_file)
    results = [group_status(group, values) for group in requirement_groups(values)]

    if args.json:
        print(json.dumps({"env_file": str(env_file), "groups": results}, indent=2))
    else:
        render_text(results, env_file)

    if args.strict:
        blocked = [item for item in results if not item["ready"] and item["name"] != "deterministic_local"]
        return 1 if blocked else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
