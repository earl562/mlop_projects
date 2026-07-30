from __future__ import annotations

from plotlot.harness.contracts import (
    ApplicabilityScope,
    CountyName,
    GISFeature,
    GISProvider,
    SourceCatalogEntry,
    SourceLane,
    SourceMode,
)


def fixture_source_catalog(_source_mode: SourceMode) -> list[SourceCatalogEntry]:
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
            source_url="https://gis-mdc.opendata.arcgis.com/",
            item_url="https://gis-mdc.opendata.arcgis.com/datasets/municipal-zoning",
            feature_service_url="https://services.arcgis.com/miami/FeatureServer/0",
            geometry_type="polygon",
            applicability_scope=ApplicabilityScope.MUNICIPAL,
            metadata={"fixture": True, "layer_family": "zoning"},
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
            source_url="https://gis-mdc.opendata.arcgis.com/",
            feature_service_url="https://services.arcgis.com/miami/FeatureServer/1",
            geometry_type="polygon",
            applicability_scope=ApplicabilityScope.PARCEL,
            metadata={"fixture": True, "layer_family": "parcel"},
        ),
        SourceCatalogEntry(
            source_id="src_broward_bmsd_zoning",
            lane=SourceLane.SOUTH_FLORIDA_GIS,
            provider=GISProvider.BROWARD_GEOHUB,
            source_type="zoning_boundary",
            jurisdiction="Broward County",
            county=CountyName("Broward"),
            dataset_name="Broward BMSD Zoning",
            layer_name="BMSD Zoning",
            source_url="https://geohub-bcgis.opendata.arcgis.com/",
            item_url="https://geohub-bcgis.opendata.arcgis.com/datasets/bmsd-zoning",
            feature_service_url="https://services.arcgis.com/broward/FeatureServer/0",
            geometry_type="polygon",
            applicability_scope=ApplicabilityScope.BMSD,
            metadata={"fixture": True, "scope": "unincorporated_or_bmsd"},
        ),
        SourceCatalogEntry(
            source_id="src_broward_city_boundaries",
            lane=SourceLane.SOUTH_FLORIDA_GIS,
            provider=GISProvider.BROWARD_GEOHUB,
            source_type="municipal_boundary",
            jurisdiction="Broward County",
            county=CountyName("Broward"),
            dataset_name="Broward Municipal Boundaries",
            layer_name="Municipalities",
            source_url="https://geohub-bcgis.opendata.arcgis.com/",
            feature_service_url="https://services.arcgis.com/broward/FeatureServer/2",
            geometry_type="polygon",
            applicability_scope=ApplicabilityScope.COUNTYWIDE,
            metadata={"fixture": True, "layer_family": "boundary"},
        ),
        SourceCatalogEntry(
            source_id="src_broward_flood_zones",
            lane=SourceLane.SOUTH_FLORIDA_GIS,
            provider=GISProvider.BROWARD_GEOHUB,
            source_type="flood_zone",
            jurisdiction="Broward County",
            county=CountyName("Broward"),
            dataset_name="Broward FEMA Flood Information",
            layer_name="Flood Zones",
            source_url="https://geohub-bcgis.opendata.arcgis.com/",
            feature_service_url="https://services.arcgis.com/broward/FeatureServer/3",
            geometry_type="polygon",
            applicability_scope=ApplicabilityScope.CONTEXTUAL,
            metadata={"fixture": True, "layer_family": "flood"},
        ),
    ]


def fixture_features(source_id: str) -> list[GISFeature]:
    match source_id:
        case "src_miami_dade_municipal_zoning":
            return [
                GISFeature(
                    feature_id="md_zoning_001",
                    attributes={"OBJECTID": 1, "ZONE": "T4-R", "MUNICIPALITY": "Miami"},
                    geometry={"type": "Polygon", "coordinates": []},
                )
            ]
        case "src_broward_bmsd_zoning":
            return [
                GISFeature(
                    feature_id="bc_bmsd_zoning_001",
                    attributes={"OBJECTID": 7, "ZONE": "RS-6", "AREA": "BMSD"},
                    geometry={"type": "Polygon", "coordinates": []},
                )
            ]
        case _:
            return [
                GISFeature(
                    feature_id=f"{source_id}_feature_001",
                    attributes={"OBJECTID": 1, "NAME": "Fixture feature"},
                    geometry={"type": "Polygon", "coordinates": []},
                )
            ]
