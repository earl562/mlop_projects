"""Pydantic models for ArcGIS Hub dataset discovery and field mapping cache."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class DatasetInfo(BaseModel):
    """Discovered ArcGIS dataset from Hub."""

    dataset_id: str
    name: str
    url: str  # FeatureServer/MapServer URL
    layer_id: int = 0
    dataset_type: str  # "parcels" | "zoning" | "sales"
    county: str
    state: str
    fips: str | None = None
    fields: list[str] = Field(default_factory=list)
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FieldMapping(BaseModel):
    """Maps a county's ArcGIS field names to PropertyRecord fields."""

    county_key: str
    mappings: dict[str, str]  # {"FOLIO": "folio", "TRUE_SITE_ADDR": "address"}
    unit_conversions: dict[str, str] = Field(default_factory=dict)  # {"ACRES": "acres_to_sqft"}
    confidence: float = 0.0
    method: str = "heuristic"  # "heuristic" | "llm" | "human"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CountyCache(BaseModel):
    """Cached county data in Firestore."""

    county_key: str
    state: str
    parcels_dataset: DatasetInfo | None = None
    zoning_dataset: DatasetInfo | None = None
    field_mapping: FieldMapping | None = None
    last_verified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_hours: int = 168  # 7 days
