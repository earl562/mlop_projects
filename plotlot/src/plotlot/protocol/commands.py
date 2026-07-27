from __future__ import annotations

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from plotlot.protocol.base import ProtocolModel
from plotlot.protocol.contexts import ActorContextV1, PlotLotHostContextV1


class OpportunitySubjectV1(ProtocolModel):
    external_id: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=5, max_length=300)
    county: Literal["miami-dade", "broward", "palm-beach", "san-diego"]
    municipality: str = Field(min_length=1, max_length=200)
    development_program_id: str = Field(min_length=1, max_length=200)
    parcel_id: str | None = Field(default=None, min_length=1, max_length=200)


class AcquisitionProfileV1(ProtocolModel):
    buyer_kind: Literal[
        "general-contractor-developer",
        "private-investor",
        "land-developer",
    ]
    strategy: Literal[
        "build-to-sell",
        "build-to-rent",
        "renovate",
        "teardown",
        "subdivision",
        "hold",
    ]
    target_margin_basis_points: int = Field(ge=0, le=10_000)
    asking_price_cents: int | None = Field(default=None, gt=0)


class OpportunityCommandV1(ProtocolModel):
    schema_version: Literal["OpportunityCommandV1"]
    host: PlotLotHostContextV1
    actor: ActorContextV1
    opportunity: OpportunitySubjectV1
    acquisition_profile: AcquisitionProfileV1
    requested_fact_families: tuple[
        Literal[
            "property-identity",
            "local-truth",
            "constraints-capacity",
            "market-evidence",
            "underwriting",
            "opportunity-analysis",
        ],
        ...,
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def actor_matches_host_tenant(self) -> Self:
        if self.actor.tenant_id != self.host.tenant_id:
            raise PydanticCustomError(
                "protocol_actor_tenant_mismatch",
                "verified actor tenant must match host tenant",
            )
        return self


class CancelRunCommandV1(ProtocolModel):
    schema_version: Literal["CancelRunCommandV1"]
    host: PlotLotHostContextV1
    actor: ActorContextV1
    engine_run_id: str = Field(pattern=r"^engrun_[A-Za-z0-9_-]+$")
    expected_revision_number: int = Field(ge=1)
    reason_code: Literal["user-requested", "deadline-exceeded", "superseded"]
    deadline_at: AwareDatetime


class ReplayRunCommandV1(ProtocolModel):
    schema_version: Literal["ReplayRunCommandV1"]
    host: PlotLotHostContextV1
    actor: ActorContextV1
    engine_run_id: str = Field(pattern=r"^engrun_[A-Za-z0-9_-]+$")
    from_revision_number: int = Field(ge=1)
    replay_mode: Literal["full", "from-failed-stage"]
    deadline_at: AwareDatetime
