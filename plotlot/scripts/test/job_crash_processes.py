#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx>=0.27",
# ]
# ///
# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: imported by the Task 11 crash harness; it is not a standalone command.
# ──────────────────

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from job_crash_errors import CrashHarnessError


@dataclass(frozen=True, slots=True)
class ProcessRestart:
    before_pid: int
    after_pid: int
    contender_pids: tuple[int, ...] | None = None
    health_before: int | None = None
    health_after: int | None = None
    killed: bool | None = None


@dataclass(frozen=True, slots=True)
class ProcessLaunch:
    process: subprocess.Popen[bytes]
    log_path: Path


@dataclass(frozen=True, slots=True)
class LaunchSpec:
    command: list[str]
    root: Path
    environment: dict[str, str]
    log_path: Path


@dataclass(frozen=True, slots=True)
class ActorSpec:
    role: str
    arguments: list[str]
    root: Path
    log_path: Path


@dataclass(frozen=True, slots=True)
class ApiSpec:
    root: Path
    database_url: str
    port: int
    log_path: Path


def launch(spec: LaunchSpec) -> ProcessLaunch:
    with spec.log_path.open("ab") as log:
        process = subprocess.Popen(
            spec.command,
            cwd=spec.root,
            env=spec.environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    return ProcessLaunch(process=process, log_path=spec.log_path)


def launch_actor(spec: ActorSpec) -> ProcessLaunch:
    return launch(
        LaunchSpec(
            command=[
                sys.executable,
                "scripts/test/job_crash_actor.py",
                spec.role,
                *spec.arguments,
            ],
            root=spec.root,
            environment=os.environ.copy(),
            log_path=spec.log_path,
        )
    )


def launch_api(spec: ApiSpec) -> ProcessLaunch:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = spec.database_url
    return launch(
        LaunchSpec(
            command=[
                sys.executable,
                "-m",
                "uvicorn",
                "plotlot.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(spec.port),
            ],
            root=spec.root,
            environment=environment,
            log_path=spec.log_path,
        )
    )


def wait_http(url: str, process: subprocess.Popen[bytes]) -> int:
    timeout = httpx.Timeout(connect=1.0, read=2.0, write=2.0, pool=1.0)
    limits = httpx.Limits(max_connections=5, max_keepalive_connections=2)
    transport = httpx.HTTPTransport(retries=1)
    with httpx.Client(
        transport=transport,
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
    ) as client:
        for _ in range(80):
            if process.poll() is not None:
                raise CrashHarnessError(f"process {process.pid} exited before readiness")
            try:
                response = client.get(url)
            except httpx.TransportError:
                time.sleep(0.1)
                continue
            if response.status_code == 200:
                return response.status_code
            time.sleep(0.1)
    raise TimeoutError(f"process {process.pid} did not serve {url}")


def terminate(launch: ProcessLaunch) -> int:
    process = launch.process
    if process.poll() is None:
        process.kill()
    return process.wait(timeout=10)
