from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

County = Literal["miami-dade", "broward", "palm-beach"]
MunicipalityLane = Literal[
    "miami",
    "miami-gardens",
    "unincorporated-miami-dade",
    "fort-lauderdale",
    "miramar",
    "hollywood",
    "west-palm-beach",
    "boca-raton",
    "unincorporated-palm-beach-loxahatchee",
]
Workflow = Literal[
    "opportunity-intake",
    "constraints-and-capacity",
    "market-underwriting",
    "decision-release",
]
FactFamily = Literal[
    "property-identity",
    "jurisdiction",
    "zoning",
    "development-constraints",
    "legal-capacity",
    "land-comps",
    "finished-resale-comps",
    "underwriting",
    "pricing-readiness",
    "reviewer-approval",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda name: "".join(
            (name.split("_")[0], *(part.title() for part in name.split("_")[1:]))
        ),
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


LANE_COUNTIES: dict[MunicipalityLane, County] = {
    "miami": "miami-dade",
    "miami-gardens": "miami-dade",
    "unincorporated-miami-dade": "miami-dade",
    "fort-lauderdale": "broward",
    "miramar": "broward",
    "hollywood": "broward",
    "west-palm-beach": "palm-beach",
    "boca-raton": "palm-beach",
    "unincorporated-palm-beach-loxahatchee": "palm-beach",
}
