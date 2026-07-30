from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from plotlot.harness.contracts.base import HarnessContract, JsonObject, SourceLane


class PolicyPermission(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ToolSpec(HarnessContract):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: JsonObject
    output_schema: JsonObject
    permission: PolicyPermission
    source_lane: SourceLane | None = None
    evidence_behavior: str = Field(min_length=1)
    timeout_seconds: int = Field(default=30, ge=1)
    retry_count: int = Field(default=0, ge=0)
    deterministic: bool
    fixture_name: str | None = None


class SkillSpec(HarnessContract):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(min_length=1)
    required_inputs: list[str]
    allowed_tools: list[str]
    allowed_source_lanes: list[SourceLane]
    required_evidence_types: list[str]
    required_calculations: list[str]
    output_schema: JsonObject
    verifier_profile: str = Field(min_length=1)
    report_template: str = Field(min_length=1)

    @model_validator(mode="after")
    def _must_have_tooling_or_sources(self) -> "SkillSpec":
        if not self.allowed_tools and not self.allowed_source_lanes:
            raise ValueError("skill must declare tools or source lanes")
        return self


class AgentRoleSpec(HarnessContract):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    allowed_tools: list[str]
    allowed_source_lanes: list[SourceLane]
    prohibited_tools: list[str]
    finalization_allowed: bool = False
    verification_required: bool = True
