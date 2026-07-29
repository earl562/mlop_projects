#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "pydantic>=2",
# ]
# ///
# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: imported by job_crash_matrix.py; it is not a standalone command.
# ──────────────────

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from job_crash_infrastructure import DatabaseContainer, DatabaseRestart
from job_crash_processes import ProcessRestart


KillPoint = Literal[
    "claimed",
    "started",
    "engine-returned",
    "outbox-written",
    "webhook-sent",
]


@dataclass(frozen=True, slots=True)
class MatrixArguments:
    workers: int
    kill_points: tuple[KillPoint, ...]
    restarts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Runtime:
    root: Path
    temporary: Path
    container: DatabaseContainer
    workers: int
    ledger_path: Path
    engine_url: str
    webhook_url: str


class EngineObservable(BaseModel):
    model_config = ConfigDict(frozen=True)

    effects: int
    attempts: int
    run_id: str
    revision_id: str
    host_link: str


class WebhookObservable(BaseModel):
    model_config = ConfigDict(frozen=True)

    effects: int
    attempts: int
    receipt_id: str


class TerminalObservable(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: int
    engine_run_id: str
    engine_revision_id: str


class OutboxObservable(BaseModel):
    model_config = ConfigDict(frozen=True)

    receipts: int
    provider_receipt_id: str
    host_link: str


class NotificationPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    host_link: str


class StageSignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    pid: int
    stage: KillPoint


class ScenarioResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    kill_point: KillPoint
    api: ProcessRestart
    worker: ProcessRestart
    database: DatabaseRestart
    engine: EngineObservable
    webhook: WebhookObservable
    terminal: TerminalObservable
    outbox: OutboxObservable


class ServiceProcesses(BaseModel):
    model_config = ConfigDict(frozen=True)

    engine_pid: int
    webhook_pid: int


class MatrixResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    workers: int
    restarts: tuple[str, ...]
    services: ServiceProcesses
    scenarios: tuple[ScenarioResult, ...]
