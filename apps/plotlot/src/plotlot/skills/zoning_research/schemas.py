"""Pydantic schemas for the zoning_research skill.

These schemas provide a stable contract surface for future harness APIs and
MCP adapters, without forcing a rewrite of the underlying pipeline.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ZoningResearchPayload(BaseModel):
    address: str | None = None
    jurisdiction: str | None = None
    parcel_id: str | None = None
    zoning_code: str | None = None
    intended_use: str | None = None


class ZoningResearchResult(BaseModel):
    report: dict[str, Any] = Field(default_factory=dict)
    evidence_candidates: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
