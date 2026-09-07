from dataclasses import dataclass
from datetime import date
from typing import Annotated, Final, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

POLICY_VERSION: Final = "reliable-comps-v1"

PositiveFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
NonBlankStr = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]
DatePrecision = Literal["day", "month", "unknown"]
PropertyType = Literal[
    "land",
    "single_family",
    "condo",
    "townhouse",
    "multifamily",
    "commercial",
    "unknown",
]
CompCategory = Literal["land", "resale", "new_construction", "incomplete", "unknown"]
TransactionStatus = Literal["closed", "active", "pending", "unknown"]
Qualification = Literal["qualified", "disqualified", "pending", "unknown"]
SourceKind = Literal["county", "recorder", "user_reviewed", "listing", "unknown"]


def _require_safe_http_url(value: str) -> str:
    if not value:
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PydanticCustomError("unsafe_url", "URL must use HTTP or HTTPS")
    return value


def _allow_reference_or_safe_http_url(value: str) -> str:
    if "://" not in value:
        return value
    return _require_safe_http_url(value)


class SaleEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: NonBlankStr
    parcel_id: str = ""
    state: NonBlankStr
    county: NonBlankStr
    address: str = ""
    sale_price: NonNegativeFiniteFloat | None = None
    sale_date: str = ""
    date_precision: DatePrecision = "unknown"
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    lot_size_sqft: PositiveFiniteFloat | None = None
    building_area_sqft: PositiveFiniteFloat | None = None
    units: Annotated[int, Field(gt=0, le=1_000_000)] | None = None
    property_type: PropertyType = "unknown"
    category: CompCategory = "unknown"
    classification_basis: str = ""
    transaction_status: TransactionStatus = "unknown"
    qualification: Qualification = "unknown"
    qualification_code: str = ""
    source_kind: SourceKind = "unknown"
    source_url: str = ""
    source_record_id: str = ""
    recorded_document: str = ""
    retrieved_at: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""
    review_notes: str = ""
    multi_parcel: bool = False
    property_changed: bool = False
    conflict_flags: tuple[str, ...] = ()
    construction_completed_date: str = ""
    completion_source: str = ""
    zoning_code: str = ""
    neighborhood: str = ""
    waterfront: bool | None = None

    _validate_source_url = field_validator("source_url")(_require_safe_http_url)
    _validate_completion_url = field_validator("completion_source")(
        _allow_reference_or_safe_http_url
    )


class CompSubject(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    parcel_id: NonBlankStr
    state: NonBlankStr
    county: NonBlankStr
    address: str = ""
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    lot_size_sqft: PositiveFiniteFloat | None = None
    building_area_sqft: PositiveFiniteFloat | None = None
    property_type: PropertyType = "land"
    category: CompCategory = "land"
    zoning_code: str = ""
    neighborhood: str = ""
    waterfront: bool | None = None


class CompPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: str
    radius_miles: Annotated[float, Field(gt=0, le=3, allow_inf_nan=False)] = 3
    months: Annotated[int, Field(ge=1, le=120)] = 12
    min_comps: Annotated[int, Field(ge=3, le=50)] = 3
    max_comps: Annotated[int, Field(ge=3, le=50)] = 5
    size_tolerance: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.3

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as error:
            raise PydanticCustomError("invalid_as_of", "as_of must be an ISO day") from error
        if len(value) != 10 or parsed.isoformat() != value:
            raise PydanticCustomError("invalid_as_of", "as_of must be an ISO day")
        return value

    @model_validator(mode="after")
    def validate_comp_counts(self) -> Self:
        if self.max_comps < self.min_comps:
            raise PydanticCustomError(
                "invalid_comp_counts", "max_comps must be greater than or equal to min_comps"
            )
        return self


@dataclass(frozen=True, slots=True)
class CompDecision:
    evidence_id: str
    parcel_id: str
    state: str
    county: str
    address: str
    sale_price: float | None
    sale_date: str
    date_precision: DatePrecision
    latitude: float | None
    longitude: float | None
    lot_size_sqft: float | None
    building_area_sqft: float | None
    units: int | None
    property_type: PropertyType
    category: CompCategory
    classification_basis: str
    transaction_status: TransactionStatus
    qualification: Qualification
    qualification_code: str
    source_kind: SourceKind
    source_url: str
    source_record_id: str
    recorded_document: str
    retrieved_at: str
    reviewed_by: str
    reviewed_at: str
    review_notes: str
    multi_parcel: bool
    property_changed: bool
    conflict_flags: tuple[str, ...]
    construction_completed_date: str
    completion_source: str
    zoning_code: str
    neighborhood: str
    waterfront: bool | None
    distance_miles: float | None
    reasons: tuple[str, ...]
    accepted: bool


@dataclass(frozen=True, slots=True)
class CompSetResult:
    status: str
    category: str
    policy_version: str
    as_of: str
    accepted: tuple[CompDecision, ...]
    rejected: tuple[CompDecision, ...]
    candidate_count: int
    value_low: float | None
    value_median: float | None
    value_high: float | None
    value_basis: str
    notes: tuple[str, ...]
