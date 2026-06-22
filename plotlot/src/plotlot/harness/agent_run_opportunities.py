from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentRunOpportunityHypothesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)
    status: Literal["hypothesis"]
    current_verified_condition: str = Field(min_length=1)
    proposed_scenario: str = Field(min_length=1)
    required_zoning_entitlement_path: str = Field(min_length=1)
    calculation_outputs: list[str] = Field(min_length=1)
    upside_mechanism: str = Field(min_length=1)
    blocking_constraints: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    next_verification_step: str = Field(min_length=1)
