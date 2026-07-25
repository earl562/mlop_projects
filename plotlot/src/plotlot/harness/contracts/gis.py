from __future__ import annotations

from typing import Protocol

from pydantic import Field

from plotlot.harness.contracts.artifacts import EvidenceItem, NormalizedGISRecord, SourceCatalogEntry
from plotlot.harness.contracts.base import (
    ApplicabilityStatus,
    CountyName,
    GISProvider,
    HarnessContract,
    JsonObject,
    RunId,
)


class GISFeature(HarnessContract):
    feature_id: str = Field(min_length=1)
    attributes: JsonObject
    geometry: JsonObject | None = None


class GISFeatureQueryResult(HarnessContract):
    source_id: str = Field(min_length=1)
    provider: GISProvider
    features: list[GISFeature]


class GISApplicabilityResult(HarnessContract):
    applicability: ApplicabilityStatus
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class GISSiteContext(HarnessContract):
    county: CountyName
    municipality: str | None = None
    is_unincorporated_or_bmsd: bool | None = None
    geometry: JsonObject | None = None


class SouthFloridaGISProviderAdapter(Protocol):
    provider: GISProvider

    async def search_datasets(self, query: str) -> list[SourceCatalogEntry]: ...

    async def query_feature_service(
        self,
        source_id: str,
        *,
        where: str,
        limit: int,
    ) -> GISFeatureQueryResult: ...

    async def normalize_feature(
        self,
        source: SourceCatalogEntry,
        feature: GISFeature,
    ) -> NormalizedGISRecord: ...

    async def create_evidence(
        self,
        source: SourceCatalogEntry,
        record: NormalizedGISRecord,
        run_id: RunId,
        *,
        site_context: GISSiteContext | None = None,
    ) -> EvidenceItem: ...
