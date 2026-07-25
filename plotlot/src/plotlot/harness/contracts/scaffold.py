from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator

from plotlot.harness.contracts.base import HarnessContract, JsonObject, utc_now


class ScaffoldComponentType(StrEnum):
    TOOL = "tool"


class ScaffoldFileStatus(StrEnum):
    CREATED = "created"
    OVERWRITTEN = "overwritten"


class ScaffoldFile(HarnessContract):
    path: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    status: ScaffoldFileStatus


class ScaffoldManifest(HarnessContract):
    scaffold_id: str = Field(min_length=1)
    component_type: ScaffoldComponentType
    name: str = Field(min_length=1)
    target_root: str = Field(min_length=1)
    files: list[ScaffoldFile]
    force: bool = False
    metadata: JsonObject = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def _created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value
