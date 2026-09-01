"""Typed contracts for reliable comparable sales and acquisition decisions."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CompStatus(StrEnum):
    QUALIFIED = "qualified"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CompConfidence(StrEnum):
    INSUFFICIENT = "insufficient"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExclusionReason(StrEnum):
    SUBJECT_PROPERTY = "subject_property"
    DUPLICATE = "duplicate"
    MISSING_PROVENANCE = "missing_provenance"
    STALE = "stale"
    OUTSIDE_RADIUS = "outside_radius"
    PROPERTY_TYPE_MISMATCH = "property_type_mismatch"
    LOT_SIZE_MISMATCH = "lot_size_mismatch"
    BUILDING_SIZE_MISMATCH = "building_size_mismatch"
    PRICE_OUTLIER = "price_outlier"


class AcquisitionDecisionStatus(StrEnum):
    ADVANCE_FOR_REVIEW = "advance_for_review"
    HOLD_FOR_INPUTS = "hold_for_inputs"
    REJECT_BUY_BOX = "reject_buy_box"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


ValuationBasis = Literal["building_sqft", "lot_sqft", "sale_price"]


class ComparableSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1, max_length=120)
    record_id: str = Field(min_length=1, max_length=240)
    source_url: str = Field(min_length=1, max_length=2_000)
    retrieved_at: datetime

    @field_validator("provider", "record_id", "source_url", mode="before")
    @classmethod
    def _strip_source_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SubjectProperty(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str = Field(min_length=1, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    property_type: str | None = Field(default=None, max_length=120)
    lot_size_sqft: float | None = Field(default=None, gt=0)
    building_sqft: float | None = Field(default=None, gt=0)

    @field_validator("address", "property_type", mode="before")
    @classmethod
    def _strip_subject_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ComparableSale(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sale_id: str = Field(min_length=1, max_length=240)
    address: str = Field(min_length=1, max_length=300)
    sale_price: float = Field(gt=0)
    sale_date: date
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    property_type: str | None = Field(default=None, max_length=120)
    lot_size_sqft: float | None = Field(default=None, gt=0)
    building_sqft: float | None = Field(default=None, gt=0)
    source: ComparableSource | None = None
    evidence_id: str | None = Field(default=None, max_length=240)

    @field_validator("sale_id", "address", "property_type", "evidence_id", mode="before")
    @classmethod
    def _strip_sale_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CompPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_age_days: int = Field(default=730, ge=1, le=3_650)
    max_distance_miles: float = Field(default=5.0, gt=0, le=100)
    min_lot_size_ratio: float = Field(default=0.5, gt=0, le=1)
    max_lot_size_ratio: float = Field(default=1.5, ge=1)
    min_building_size_ratio: float = Field(default=0.6, gt=0, le=1)
    max_building_size_ratio: float = Field(default=1.4, ge=1)
    min_comps: int = Field(default=3, ge=3, le=20)
    outlier_modified_z: float = Field(default=3.5, gt=0, le=20)

    @model_validator(mode="after")
    def _validate_ratio_ranges(self) -> "CompPolicy":
        if self.min_lot_size_ratio > self.max_lot_size_ratio:
            raise ValueError("lot size ratio range is invalid")
        if self.min_building_size_ratio > self.max_building_size_ratio:
            raise ValueError("building size ratio range is invalid")
        return self


class QualifiedComparable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sale: ComparableSale
    distance_miles: float | None = Field(default=None, ge=0)
    age_days: int = Field(ge=0)
    normalized_price: float = Field(gt=0)


class ExcludedComparable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sale_id: str
    address: str
    reasons: tuple[ExclusionReason, ...] = Field(min_length=1)


class CompSetResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: CompStatus
    confidence: CompConfidence
    qualified: tuple[QualifiedComparable, ...] = ()
    excluded: tuple[ExcludedComparable, ...] = ()
    valuation_basis: ValuationBasis | None = None
    valuation_low: float | None = Field(default=None, ge=0)
    valuation_median: float | None = Field(default=None, ge=0)
    valuation_high: float | None = Field(default=None, ge=0)
    evidence_ids: tuple[str, ...] = ()
    message: str = ""


class AcquisitionDecisionInputs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    purchase_price: float | None = Field(default=None, ge=0)
    comps: CompSetResult
    residual_land_value: float | None = Field(default=None, ge=0)


class AcquisitionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: AcquisitionDecisionStatus
    purchase_price: float | None = Field(default=None, ge=0)
    comp_floor: float | None = Field(default=None, ge=0)
    residual_ceiling: float | None = Field(default=None, ge=0)
    supported_basis: float | None = Field(default=None, ge=0)
    cushion_dollars: float | None = None
    cushion_percent: float | None = None
    pricing_signal: str
    reasons: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


__all__ = [
    "AcquisitionDecision",
    "AcquisitionDecisionInputs",
    "AcquisitionDecisionStatus",
    "ComparableSale",
    "ComparableSource",
    "CompConfidence",
    "CompPolicy",
    "CompSetResult",
    "CompStatus",
    "ExcludedComparable",
    "ExclusionReason",
    "QualifiedComparable",
    "SubjectProperty",
    "ValuationBasis",
]
