"""Workspace and harness request schemas.

These schemas are an internal contract surface for the workspace-native harness
layer. The CRUD routes may evolve independently, but the harness run request
should remain stable.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str
    slug: str | None = None


class ProjectCreate(BaseModel):
    workspace_id: str | None = None
    name: str
    project_type: str = "zoning_research"
    criteria: dict[str, Any] = Field(default_factory=dict)


class SiteCreate(BaseModel):
    project_id: str
    label: str
    address: str | None = None
    parcel_id: str | None = None
    lat: float | None = None
    lng: float | None = None


class HarnessRunRequest(BaseModel):
    workspace_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    skill: str | None = None
    intent: str | None = None
    prompt: str
    payload: dict[str, Any] = Field(default_factory=dict)
