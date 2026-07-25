from __future__ import annotations

import httpx

from plotlot.harness.contracts import (
    ApplicabilityScope,
    CountyName,
    GISFeature,
    GISFeatureQueryResult,
    GISProvider,
    SourceCatalogEntry,
    SourceLane,
)
from plotlot.observability.tracing import start_otel_span
from plotlot.retrieval.property import (
    BROWARD_PARCELS_URL,
    BROWARD_ZONING_URL,
    MDC_MUNICIPAL_ZONING_URL,
    MDC_PROPERTY_BOUNDARIES_URL,
)


def live_source_catalog() -> list[SourceCatalogEntry]:
    return [
        SourceCatalogEntry(
            source_id="src_miami_dade_municipal_zoning",
            lane=SourceLane.SOUTH_FLORIDA_GIS,
            provider=GISProvider.MIAMI_DADE_ARCGIS,
            source_type="zoning_boundary",
            jurisdiction="Miami-Dade County",
            county=CountyName("Miami-Dade"),
            dataset_name="Miami-Dade Municipal Zoning Districts",
            layer_name="Municipal Zoning",
            source_url="https://gisweb.miamidade.gov/arcgis/rest/services/LandManagement/MD_Zoning/MapServer/2",
            item_url="https://gis-mdc.opendata.arcgis.com/",
            feature_service_url=MDC_MUNICIPAL_ZONING_URL,
            geometry_type="polygon",
            applicability_scope=ApplicabilityScope.MUNICIPAL,
            metadata={"fixture": False, "live": True, "layer_family": "zoning"},
        ),
        SourceCatalogEntry(
            source_id="src_miami_dade_parcels",
            lane=SourceLane.SOUTH_FLORIDA_GIS,
            provider=GISProvider.MIAMI_DADE_ARCGIS,
            source_type="parcel_record",
            jurisdiction="Miami-Dade County",
            county=CountyName("Miami-Dade"),
            dataset_name="Miami-Dade Parcel Boundaries",
            layer_name="Parcels",
            source_url="https://gisweb.miamidade.gov/arcgis/rest/services/LandManagement/MD_ZoningLandManagementViewer/MapServer/2",
            item_url="https://gis-mdc.opendata.arcgis.com/",
            feature_service_url=MDC_PROPERTY_BOUNDARIES_URL,
            geometry_type="polygon",
            applicability_scope=ApplicabilityScope.PARCEL,
            metadata={"fixture": False, "live": True, "layer_family": "parcel"},
        ),
        SourceCatalogEntry(
            source_id="src_broward_bmsd_zoning",
            lane=SourceLane.SOUTH_FLORIDA_GIS,
            provider=GISProvider.BROWARD_GEOHUB,
            source_type="zoning_boundary",
            jurisdiction="Broward County",
            county=CountyName("Broward"),
            dataset_name="Broward County Zoning",
            layer_name="County Zoning",
            source_url="https://gisweb-adapters.bcpa.net/arcgis/rest/services/BCPA_EXTERNAL_JAN26/MapServer/9",
            item_url="https://geohub-bcgis.opendata.arcgis.com/",
            feature_service_url=BROWARD_ZONING_URL,
            geometry_type="polygon",
            applicability_scope=ApplicabilityScope.BMSD,
            metadata={"fixture": False, "live": True, "scope": "unincorporated_or_bmsd"},
        ),
        SourceCatalogEntry(
            source_id="src_broward_city_boundaries",
            lane=SourceLane.SOUTH_FLORIDA_GIS,
            provider=GISProvider.BROWARD_GEOHUB,
            source_type="municipal_boundary",
            jurisdiction="Broward County",
            county=CountyName("Broward"),
            dataset_name="Broward Parcel Boundaries",
            layer_name="Parcels",
            source_url="https://gisweb-adapters.bcpa.net/arcgis/rest/services/BCPA_EXTERNAL_JAN26/MapServer/16",
            item_url="https://geohub-bcgis.opendata.arcgis.com/",
            feature_service_url=BROWARD_PARCELS_URL,
            geometry_type="polygon",
            applicability_scope=ApplicabilityScope.COUNTYWIDE,
            metadata={"fixture": False, "live": True, "layer_family": "boundary"},
        ),
    ]


async def query_live_feature_service(
    source: SourceCatalogEntry,
    *,
    where: str,
    limit: int,
) -> GISFeatureQueryResult:
    if not source.feature_service_url:
        return GISFeatureQueryResult(source_id=source.source_id, provider=source.provider, features=[])
    with start_otel_span(
        "plotlot.harness.south_florida_gis.query_live_feature_service",
        {
            "plotlot.gis.source_id": source.source_id,
            "plotlot.gis.provider": str(source.provider),
            "plotlot.gis.limit": limit,
        },
    ):
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                _query_url(source.feature_service_url),
                params={
                    "f": "json",
                    "where": where,
                    "outFields": "*",
                    "returnGeometry": "true",
                    "resultRecordCount": max(1, limit),
                },
            )
            response.raise_for_status()
            payload = response.json()
    features_payload = payload.get("features")
    if not isinstance(features_payload, list):
        return GISFeatureQueryResult(source_id=source.source_id, provider=source.provider, features=[])
    features = [
        GISFeature(
            feature_id=str(
                feature.get("attributes", {}).get("OBJECTID")
                or feature.get("attributes", {}).get("FID")
                or f"{source.source_id}_{index}"
            ),
            attributes=feature.get("attributes", {}),
            geometry=feature.get("geometry", {}),
        )
        for index, feature in enumerate(features_payload)
        if isinstance(feature, dict)
    ]
    return GISFeatureQueryResult(source_id=source.source_id, provider=source.provider, features=features)


def _query_url(feature_service_url: str) -> str:
    return feature_service_url if feature_service_url.endswith("/query") else f"{feature_service_url}/query"
