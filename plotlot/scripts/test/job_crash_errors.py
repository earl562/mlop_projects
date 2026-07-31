#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: imported by the Task 11 crash harness; it is not a standalone command.
# ──────────────────

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CrashHarnessError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail
