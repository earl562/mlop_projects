#!/usr/bin/env python3
"""Programmatically populate PlotLot live-test credentials via CLIs.

This helper never prints secret values. It updates `.env` keys in place and reports:
- which keys were updated
- which keys were skipped

Supported sources:
1) Existing shell env vars (`--from-env KEY`)
2) 1Password CLI (`--op KEY=op://vault/item/field`)
3) Google Secret Manager via gcloud (`--gcloud KEY=secret[:version]`)
4) Vercel project env vars (`--from-vercel`)

Examples:
  # pull selected secrets from your shell and enable Codex OAuth fallback
  python scripts/bootstrap_live_auth.py \\
    --from-env GEOCODIO_API_KEY \\
    --from-env JINA_API_KEY \\
    --enable-codex-oauth

  # import from 1Password references
  python scripts/bootstrap_live_auth.py \\
    --op GEOCODIO_API_KEY=op://PlotLot/Geocodio/api_key \\
    --op JINA_API_KEY=op://PlotLot/Jina/api_key

  # import from Vercel development env vars (linked frontend project)
  python scripts/bootstrap_live_auth.py --from-vercel --vercel-environment development
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


KNOWN_LIVE_KEYS = (
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_ACCESS_TOKEN",
    "NVIDIA_API_KEY",
    "GROQ_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEOCODIO_API_KEY",
    "JINA_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_PRO_PRICE_ID",
    "STRIPE_WEBHOOK_SECRET",
    "FAL_KEY",
    "HF_TOKEN",
    "CLERK_JWKS_URL",
    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
    "CLERK_SECRET_KEY",
    "DATABASE_URL",
)

ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = ENV_LINE_RE.match(raw)
        if not match:
            continue
        key = match.group(1)
        value = match.group(2).strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1].replace('\\"', '"')
        elif value.startswith("'") and value.endswith("'") and len(value) >= 2:
            value = value[1:-1]
        values[key] = value
    return values


def encode_env_value(value: str) -> str:
    if value == "":
        return ""
    if any(ch.isspace() for ch in value) or "#" in value or '"' in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


@dataclass
class EnvFileEditor:
    path: Path
    lines: list[str]
    key_index: dict[str, int]

    @classmethod
    def load(cls, path: Path) -> "EnvFileEditor":
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
        else:
            lines = []
        key_index: dict[str, int] = {}
        for idx, line in enumerate(lines):
            match = ENV_LINE_RE.match(line)
            if match:
                key_index[match.group(1)] = idx
        return cls(path=path, lines=lines, key_index=key_index)

    def set(self, key: str, value: str) -> None:
        line = f"{key}={encode_env_value(value)}"
        if key in self.key_index:
            self.lines[self.key_index[key]] = line
            return
        if self.lines and self.lines[-1].strip():
            self.lines.append("")
        self.lines.append(line)
        self.key_index[key] = len(self.lines) - 1

    def save(self) -> None:
        text = "\n".join(self.lines).rstrip() + "\n"
        self.path.write_text(text, encoding="utf-8")


def parse_key_value(raw: str, flag: str) -> tuple[str, str]:
    if "=" not in raw:
        raise ValueError(f"{flag} expects KEY=VALUE, got: {raw!r}")
    key, value = raw.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not ENV_KEY_RE.match(key):
        raise ValueError(f"Invalid env key {key!r}")
    return key, value


def run_capture(cmd: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.rstrip("\n")


def import_from_vercel(
    *,
    cwd: Path,
    environment: str,
    keys: set[str] | None,
) -> dict[str, str]:
    with tempfile.NamedTemporaryFile(prefix="plotlot-vercel-env-", suffix=".local", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        run_capture(
            [
                "vercel",
                "env",
                "pull",
                str(tmp_path),
                "--yes",
                f"--environment={environment}",
            ],
            cwd=cwd,
        )
        pulled = parse_env_file(tmp_path)
        if keys is None:
            return pulled
        return {k: v for k, v in pulled.items() if k in keys}
    finally:
        tmp_path.unlink(missing_ok=True)


def import_from_1password(refs: list[str]) -> dict[str, str]:
    imported: dict[str, str] = {}
    for raw in refs:
        key, ref = parse_key_value(raw, "--op")
        value = run_capture(["op", "read", ref])
        imported[key] = value
    return imported


def import_from_gcloud(refs: list[str]) -> dict[str, str]:
    imported: dict[str, str] = {}
    for raw in refs:
        key, secret_ref = parse_key_value(raw, "--gcloud")
        if ":" in secret_ref:
            secret_name, version = secret_ref.rsplit(":", 1)
            version = version.strip() or "latest"
        else:
            secret_name, version = secret_ref, "latest"
        value = run_capture(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                version,
                f"--secret={secret_name}",
                "--quiet",
            ],
        )
        imported[key] = value
    return imported


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env", help="Path to the env file to update")
    parser.add_argument(
        "--from-env",
        action="append",
        default=[],
        metavar="KEY",
        help="Copy KEY from current shell environment into the env file (repeatable)",
    )
    parser.add_argument(
        "--op",
        action="append",
        default=[],
        metavar="KEY=op://...",
        help="Import secret from 1Password CLI reference via `op read` (repeatable)",
    )
    parser.add_argument(
        "--gcloud",
        action="append",
        default=[],
        metavar="KEY=secret[:version]",
        help="Import secret via `gcloud secrets versions access` (repeatable)",
    )
    parser.add_argument(
        "--from-vercel",
        action="store_true",
        help="Pull env vars from linked Vercel project with `vercel env pull`",
    )
    parser.add_argument(
        "--vercel-cwd",
        default="frontend",
        help="Working directory that is linked to Vercel project (default: frontend)",
    )
    parser.add_argument(
        "--vercel-environment",
        choices=("development", "preview", "production"),
        default="development",
        help="Vercel environment for --from-vercel (default: development)",
    )
    parser.add_argument(
        "--vercel-keys",
        default=",".join(KNOWN_LIVE_KEYS),
        help="Comma-separated keys to import from Vercel; use '*' for all",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Directly set KEY=VALUE in env file (repeatable)",
    )
    parser.add_argument(
        "--enable-codex-oauth",
        action="store_true",
        help="Set PLOTLOT_USE_CODEX_OAUTH=1 and PLOTLOT_CODEX_AUTH_FILE path",
    )
    parser.add_argument(
        "--codex-auth-file",
        default="~/.codex/auth.json",
        help="Path for PLOTLOT_CODEX_AUTH_FILE when --enable-codex-oauth is used",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without writing the env file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_path = Path(args.env_file)
    editor = EnvFileEditor.load(env_path)

    updates: dict[str, str] = {}
    skipped: list[str] = []

    for key in args.from_env:
        if not ENV_KEY_RE.match(key):
            raise SystemExit(f"Invalid --from-env key: {key}")
        value = os.environ.get(key, "")
        if not value:
            skipped.append(f"{key} (missing in shell env)")
            continue
        updates[key] = value

    for raw in args.set:
        key, value = parse_key_value(raw, "--set")
        updates[key] = value

    if args.op:
        updates.update(import_from_1password(args.op))

    if args.gcloud:
        updates.update(import_from_gcloud(args.gcloud))

    if args.from_vercel:
        wanted_keys: set[str] | None
        if args.vercel_keys.strip() == "*":
            wanted_keys = None
        else:
            wanted_keys = {k.strip() for k in args.vercel_keys.split(",") if k.strip()}
        updates.update(
            import_from_vercel(
                cwd=Path(args.vercel_cwd),
                environment=args.vercel_environment,
                keys=wanted_keys,
            ),
        )

    if args.enable_codex_oauth:
        updates["PLOTLOT_USE_CODEX_OAUTH"] = "1"
        updates["PLOTLOT_CODEX_AUTH_FILE"] = args.codex_auth_file

    if not updates:
        print("No updates to apply.")
        if skipped:
            print("Skipped:")
            for item in skipped:
                print(f"- {item}")
        return 0

    for key, value in sorted(updates.items()):
        editor.set(key, value)

    if args.dry_run:
        print("Dry run (no file written). Keys that would be updated:")
        for key in sorted(updates):
            print(f"- {key}")
    else:
        editor.save()
        print(f"Updated {env_path} with {len(updates)} key(s):")
        for key in sorted(updates):
            print(f"- {key}")

    if skipped:
        print("Skipped:")
        for item in skipped:
            print(f"- {item}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
