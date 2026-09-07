#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:3003"
AUTH_KEYS = (
    "CLERK_SECRET_KEY",
    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
    "PLOTLOT_TEST_AUTH_BYPASS",
)


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2):
            return True
    except urllib.error.HTTPError as error:
        return error.code < 500
    except (OSError, urllib.error.URLError):
        return False


def stop_server(server: subprocess.Popen[bytes]) -> None:
    if server.poll() is not None:
        return
    os.killpg(server.pid, signal.SIGTERM)
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(server.pid, signal.SIGKILL)
        server.wait(timeout=10)


def main() -> int:
    environment = os.environ.copy()
    for key in AUTH_KEYS:
        environment.pop(key, None)
    environment.update(
        {
            "NEXT_PUBLIC_API_URL": "http://127.0.0.1:8000",
            "PLAYWRIGHT_BASE_URL": BASE_URL,
            "PLAYWRIGHT_DISABLE_WEBSERVER": "1",
            "PLOTLOT_MATRIX_LANE": "no-db",
            "PLOTLOT_RELEASE_GATE": "1",
        }
    )
    server = subprocess.Popen(
        ["npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3003"],
        env=environment,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if server.poll() is not None:
                return server.returncode or 1
            if server_ready():
                break
            time.sleep(0.25)
        else:
            print("PAIR_PLAYWRIGHT_DEV_SERVER_TIMEOUT", file=sys.stderr)
            return 1
        result = subprocess.run(
            ["npx", "playwright", "test", "--project=no-db", "--reporter=json,html"],
            check=False,
            env=environment,
            timeout=900,
        )
        return result.returncode
    finally:
        stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())
