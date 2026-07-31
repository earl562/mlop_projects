#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path

FORBIDDEN_MARKERS = (b"PLOTLOT_TEST_AUTH_BYPASS", b"PLAYWRIGHT_TESTING")
AUTH_KEYS = ("CLERK_SECRET_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")


def verify_no_bypass_markers(root: Path) -> None:
    for relative in ("src", ".next/standalone"):
        for path in (root / relative).rglob("*"):
            if (
                path.is_file()
                and path.suffix in {".cjs", ".js", ".map", ".mjs", ".ts", ".tsx"}
                and any(marker in path.read_bytes() for marker in FORBIDDEN_MARKERS)
            ):
                raise RuntimeError(f"test-only auth marker in production surface: {path}")


def verify_production_fails_closed(root: Path) -> None:
    environment = os.environ.copy()
    for key in AUTH_KEYS:
        environment.pop(key, None)
    environment.update({"HOSTNAME": "127.0.0.1", "PORT": "3013"})
    servers = [
        path
        for path in (
            root / ".next/standalone/server.js",
            root / ".next/standalone/plotlot/frontend/server.js",
        )
        if path.is_file()
    ]
    if len(servers) != 1:
        raise RuntimeError("production standalone server artifact is missing or ambiguous")
    try:
        result = subprocess.run(
            ["node", str(servers[0])],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("production server accepted missing auth configuration") from error
    output = result.stdout + result.stderr
    if result.returncode == 0 or b"Production startup requires complete Clerk configuration" not in output:
        raise RuntimeError("production server did not fail closed on missing auth configuration")


def main() -> int:
    root = Path.cwd()
    verify_no_bypass_markers(root)
    verify_production_fails_closed(root)
    print("PAIR_FRONTEND_AUTH_BOUNDARY_OK=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
