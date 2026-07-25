from __future__ import annotations

from dataclasses import dataclass

from pydantic import JsonValue

from plotlot.harness.contracts import (
    ApplicabilityScope,
    ApplicabilityStatus,
    CountyName,
    EvidenceId,
    EvidenceItem,
    EvidenceSourceType,
    FreshnessStatus,
    GISApplicabilityResult,
    GISFeature,
    GISFeatureQueryResult,
    GISProvider,
    GISSiteContext,
    JsonObject,
    NormalizedGISRecord,
    RunId,
    SourceCatalogEntry,
    SourceMode,
)
from plotlot.harness.south_florida_gis_fixtures import fixture_features, fixture_source_catalog
from plotlot.harness.south_florida_gis_live import live_source_catalog, query_live_feature_service


@dataclass(frozen=True, slots=True)
class MissingGISCountyError(Exception):
    source_id: str

    def __str__(self) -> str:
        return f"GIS source {self.source_id!r} is missing county metadata"


def load_south_florida_gis_source_catalog(
    source_mode: SourceMode = SourceMode.FIXTURE,
) -> list[SourceCatalogEntry]:
    if source_mode is SourceMode.LIVE:
        return live_source_catalog()
    return fixture_source_catalog(SourceMode.FIXTURE)


def search_south_florida_gis(
    query: str,
    *,
    county: CountyName | None = None,
    provider: GISProvider | None = None,
    source_mode: SourceMode = SourceMode.FIXTURE,
) -> list[SourceCatalogEntry]:
    query_text = query.casefold()
    return [
        entry
        for entry in load_south_florida_gis_source_catalog(source_mode)
        if _matches_entry(entry, query_text, county, provider)
    ]


def get_gis_source_metadata(
    source_id: str,
    *,
    source_mode: SourceMode = SourceMode.FIXTURE,
) -> SourceCatalogEntry:
    for entry in load_south_florida_gis_source_catalog(source_mode):
        if entry.source_id == source_id:
            return entry
    raise KeyError(source_id)


def resolve_site_boundary_context(
    *,
    county: CountyName,
    municipality: str | None,
    source_mode: SourceMode = SourceMode.FIXTURE,
) -> JsonObject:
    normalized_municipality = municipality.strip() if isinstance(municipality, str) else ""
    is_broward = county == CountyName("Broward")
    is_miami_dade = county == CountyName("Miami-Dade")
    is_unincorporated_or_bmsd = is_broward and normalized_municipality.casefold() in {
        "bmsd",
        "unincorporated",
        "unincorporated broward",
    }
    recommended_zoning_sources: list[str] = []
    contextual_sources: list[str] = []
    controlling_zoning_authority = "unknown"
    controlling_zoning_jurisdiction: str | None = None
    zoning_record_applicability = ApplicabilityStatus.UNKNOWN
    for entry in load_south_florida_gis_source_catalog(source_mode):
        if entry.county != county:
            continue
        if entry.source_type == "zoning_boundary":
            if is_miami_dade and entry.provider is GISProvider.MIAMI_DADE_ARCGIS:
                recommended_zoning_sources.append(entry.source_id)
            elif is_unincorporated_or_bmsd and entry.provider is GISProvider.BROWARD_GEOHUB:
                recommended_zoning_sources.append(entry.source_id)
        elif entry.applicability_scope is ApplicabilityScope.CONTEXTUAL:
            contextual_sources.append(entry.source_id)
    warning = ""
    if is_miami_dade and normalized_municipality:
        controlling_zoning_authority = "municipal"
        controlling_zoning_jurisdiction = normalized_municipality
        zoning_record_applicability = ApplicabilityStatus.DIRECT
    elif is_miami_dade:
        warning = (
            "Miami-Dade zoning lookups require municipal jurisdiction confirmation before "
            "entitlement conclusions."
        )
        controlling_zoning_jurisdiction = county
        zoning_record_applicability = ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION
    elif is_broward and is_unincorporated_or_bmsd:
        controlling_zoning_authority = "county"
        controlling_zoning_jurisdiction = normalized_municipality or county
        zoning_record_applicability = ApplicabilityStatus.DIRECT
    elif is_broward:
        warning = (
            "Broward county zoning layers are contextual for municipal parcels; use municipal zoning "
            "code or GIS for entitlement standards."
        )
        controlling_zoning_authority = "municipal"
        controlling_zoning_jurisdiction = normalized_municipality or county
        zoning_record_applicability = ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION
    return {
        "county": county,
        "municipality": normalized_municipality or None,
        "is_unincorporated_or_bmsd": is_unincorporated_or_bmsd,
        "recommended_zoning_source_ids": recommended_zoning_sources,
        "contextual_source_ids": contextual_sources,
        "controlling_zoning_authority": controlling_zoning_authority,
        "controlling_zoning_jurisdiction": controlling_zoning_jurisdiction,
        "zoning_record_applicability": zoning_record_applicability.value,
        "warning": warning,
    }


def query_gis_feature_service(
    source_id: str,
    *,
    where: str,
    limit: int,
    source_mode: SourceMode = SourceMode.FIXTURE,
) -> GISFeatureQueryResult:
    source = get_gis_source_metadata(source_id, source_mode=source_mode)
    if source_mode is SourceMode.LIVE:
        raise RuntimeError("live GIS feature service queries must use query_gis_feature_service_async")
    features = fixture_features(source_id)[:limit]
    return GISFeatureQueryResult(source_id=source_id, provider=source.provider, features=features)


async def query_gis_feature_service_async(
    source_id: str,
    *,
    where: str,
    limit: int,
    source_mode: SourceMode = SourceMode.FIXTURE,
) -> GISFeatureQueryResult:
    source = get_gis_source_metadata(source_id, source_mode=source_mode)
    if source_mode is SourceMode.LIVE:
        return await query_live_feature_service(source, where=where, limit=limit)
    features = fixture_features(source_id)[:limit]
    return GISFeatureQueryResult(source_id=source_id, provider=source.provider, features=features)


def classify_gis_applicability(
    source: SourceCatalogEntry,
    site_context: GISSiteContext,
) -> GISApplicabilityResult:
    if source.source_id == "src_broward_bmsd_zoning":
        if site_context.is_unincorporated_or_bmsd is True:
            return GISApplicabilityResult(
                applicability=ApplicabilityStatus.DIRECT,
                reason="BMSD zoning source matches an unincorporated or BMSD site.",
                confidence=0.9,
            )
        return GISApplicabilityResult(
            applicability=ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION,
            reason="BMSD zoning is contextual for Broward municipal parcels; use municipal zoning.",
            confidence=0.85,
        )
    if source.applicability_scope is ApplicabilityScope.CONTEXTUAL:
        return GISApplicabilityResult(
            applicability=ApplicabilityStatus.CONTEXTUAL,
            reason="Countywide context layer, not direct entitlement evidence.",
            confidence=0.8,
        )
    return GISApplicabilityResult(
        applicability=ApplicabilityStatus.DIRECT,
        reason="Fixture source is scoped to the selected county and layer type.",
        confidence=0.8,
    )


class MiamiDadeGISAdapter:
    provider = GISProvider.MIAMI_DADE_ARCGIS

    def __init__(self, source_mode: SourceMode = SourceMode.FIXTURE) -> None:
        self.source_mode = source_mode

    async def search_datasets(self, query: str) -> list[SourceCatalogEntry]:
        return search_south_florida_gis(query, provider=self.provider, source_mode=self.source_mode)

    async def query_feature_service(
        self,
        source_id: str,
        *,
        where: str,
        limit: int,
    ) -> GISFeatureQueryResult:
        return await query_gis_feature_service_async(
            source_id,
            where=where,
            limit=limit,
            source_mode=self.source_mode,
        )

    async def normalize_feature(
        self,
        source: SourceCatalogEntry,
        feature: GISFeature,
    ) -> NormalizedGISRecord:
        return _normalize_feature(source, feature, self.provider)

    async def create_evidence(
        self,
        source: SourceCatalogEntry,
        record: NormalizedGISRecord,
        run_id: RunId,
        *,
        site_context: GISSiteContext | None = None,
    ) -> EvidenceItem:
        return _create_gis_evidence(source, record, run_id, self.source_mode, site_context)


class BrowardGeoHubAdapter(MiamiDadeGISAdapter):
    provider = GISProvider.BROWARD_GEOHUB


def _matches_entry(
    entry: SourceCatalogEntry,
    query_text: str,
    county: CountyName | None,
    provider: GISProvider | None,
) -> bool:
    text = f"{entry.dataset_name} {entry.layer_name or ''} {entry.source_type}".casefold()
    county_matches = county is None or entry.county == county
    provider_matches = provider is None or entry.provider == provider
    return query_text in text and county_matches and provider_matches


def _normalize_feature(
    source: SourceCatalogEntry,
    feature: GISFeature,
    provider: GISProvider,
) -> NormalizedGISRecord:
    county = _require_county(source)
    return NormalizedGISRecord(
        record_id=f"rec_{feature.feature_id}",
        source_id=source.source_id,
        provider=provider,
        jurisdiction=source.jurisdiction,
        county=county,
        municipality=_string_value(feature.attributes.get("MUNICIPALITY")),
        normalized_type=_normalized_type(source),
        normalized_payload=feature.attributes,
        geometry=feature.geometry,
        spatial_reference="EPSG:4326",
        confidence=0.86,
    )


def _create_gis_evidence(
    source: SourceCatalogEntry,
    record: NormalizedGISRecord,
    run_id: RunId,
    source_mode: SourceMode,
    site_context: GISSiteContext | None,
) -> EvidenceItem:
    applicability = classify_gis_applicability(
        source,
        site_context or GISSiteContext(county=record.county, municipality=record.municipality),
    )
    freshness = FreshnessStatus.UNKNOWN if source_mode is SourceMode.LIVE else FreshnessStatus.FIXTURE
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_{record.record_id}"),
        run_id=run_id,
        source_type=EvidenceSourceType.ARCGIS_FEATURE,
        source_name=source.dataset_name,
        source_url=source.source_url,
        source_identifier=record.record_id,
        provider=record.provider,
        jurisdiction=record.jurisdiction,
        county=record.county,
        municipality=record.municipality,
        freshness_status=freshness,
        applicability=applicability.applicability,
        structured_payload={
            "record": record.normalized_payload,
            "layer_name": source.layer_name,
            "applicability_reason": applicability.reason,
        },
        geometry=record.geometry,
        confidence=applicability.confidence,
        source_mode=source_mode,
        metadata={"feature_service_url": source.feature_service_url},
    )


def _normalized_type(source: SourceCatalogEntry) -> str:
    if "zoning" in source.source_type:
        return "zoning"
    return source.source_type


def _require_county(source: SourceCatalogEntry) -> CountyName:
    if source.county is None:
        raise MissingGISCountyError(source.source_id)
    return source.county


def _string_value(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return value
    return None
