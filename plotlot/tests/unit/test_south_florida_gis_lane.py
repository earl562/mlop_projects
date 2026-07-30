from __future__ import annotations

import pytest

from plotlot.harness.contracts import (
    ApplicabilityStatus,
    CountyName,
    FreshnessStatus,
    GISProvider,
    RunId,
    SourceMode,
)
from plotlot.harness.south_florida_gis import (
    BrowardGeoHubAdapter,
    GISSiteContext,
    MiamiDadeGISAdapter,
    classify_gis_applicability,
    get_gis_source_metadata,
    load_south_florida_gis_source_catalog,
    query_gis_feature_service,
    query_gis_feature_service_async,
    resolve_site_boundary_context,
    search_south_florida_gis,
)


def test_south_florida_catalog_loads_miami_dade_and_broward_sources() -> None:
    # Given / When: the fixture-backed South Florida GIS catalog is loaded.
    catalog = load_south_florida_gis_source_catalog(SourceMode.FIXTURE)

    # Then: the lane has one shared catalog with provider-specific entries.
    providers = {entry.provider for entry in catalog}
    assert GISProvider.MIAMI_DADE_ARCGIS in providers
    assert GISProvider.BROWARD_GEOHUB in providers
    assert any(entry.dataset_name == "Miami-Dade Municipal Zoning Districts" for entry in catalog)
    assert any(entry.dataset_name == "Broward BMSD Zoning" for entry in catalog)


def test_south_florida_live_catalog_uses_non_fixture_sources() -> None:
    catalog = load_south_florida_gis_source_catalog(SourceMode.LIVE)

    assert catalog
    assert all(entry.metadata.get("fixture") is False for entry in catalog)
    assert any("gisweb.miamidade.gov" in entry.source_url for entry in catalog)
    assert any("gisweb-adapters.bcpa.net" in entry.source_url for entry in catalog)


def test_search_south_florida_gis_filters_by_county_and_query() -> None:
    # Given: the shared catalog contains multiple counties.
    county = CountyName("Miami-Dade")

    # When: an analyst searches for zoning in Miami-Dade.
    results = search_south_florida_gis("zoning", county=county, source_mode=SourceMode.FIXTURE)

    # Then: only Miami-Dade zoning records are returned.
    assert results
    assert {entry.county for entry in results} == {county}
    assert all("zoning" in f"{entry.dataset_name} {entry.layer_name}".lower() for entry in results)


def test_broward_bmsd_zoning_is_contextual_for_municipal_site() -> None:
    # Given: a Broward municipal site and the BMSD zoning layer.
    source = next(
        entry
        for entry in load_south_florida_gis_source_catalog(SourceMode.FIXTURE)
        if entry.source_id == "src_broward_bmsd_zoning"
    )
    site = GISSiteContext(
        county=CountyName("Broward"),
        municipality="Fort Lauderdale",
        is_unincorporated_or_bmsd=False,
    )

    # When: the shared applicability classifier evaluates the source.
    result = classify_gis_applicability(source, site)

    # Then: BMSD zoning is not entitlement evidence inside a municipality.
    assert result.applicability is ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION
    assert "municipal zoning" in result.reason.lower()


def test_broward_bmsd_zoning_is_direct_for_bmsd_site() -> None:
    # Given: a BMSD site and the BMSD zoning layer.
    source = next(
        entry
        for entry in load_south_florida_gis_source_catalog(SourceMode.FIXTURE)
        if entry.source_id == "src_broward_bmsd_zoning"
    )
    site = GISSiteContext(
        county=CountyName("Broward"),
        municipality=None,
        is_unincorporated_or_bmsd=True,
    )

    # When: the shared applicability classifier evaluates the source.
    result = classify_gis_applicability(source, site)

    # Then: the source can be used as direct zoning evidence.
    assert result.applicability is ApplicabilityStatus.DIRECT


@pytest.mark.asyncio
async def test_miami_dade_adapter_normalizes_fixture_feature_to_evidence() -> None:
    # Given: the Miami-Dade fixture adapter and a zoning source.
    adapter = MiamiDadeGISAdapter(source_mode=SourceMode.FIXTURE)
    source = next(
        entry
        for entry in load_south_florida_gis_source_catalog(SourceMode.FIXTURE)
        if entry.source_id == "src_miami_dade_municipal_zoning"
    )

    # When: a feature is queried, normalized, and converted to evidence.
    query = await adapter.query_feature_service(source.source_id, where="1=1", limit=1)
    normalized = await adapter.normalize_feature(source, query.features[0])
    evidence = await adapter.create_evidence(source, normalized, RunId("run_fixture_001"))

    # Then: the record and evidence carry source metadata and fixture mode.
    assert normalized.provider is GISProvider.MIAMI_DADE_ARCGIS
    assert normalized.normalized_type == "zoning"
    assert evidence.provider == "miami_dade_arcgis"
    assert evidence.source_mode is SourceMode.FIXTURE
    assert evidence.applicability is ApplicabilityStatus.DIRECT


@pytest.mark.asyncio
async def test_broward_adapter_marks_municipal_bmsd_feature_as_requires_verification() -> None:
    # Given: a municipal Broward site and the fixture adapter.
    adapter = BrowardGeoHubAdapter(source_mode=SourceMode.FIXTURE)
    source = next(
        entry
        for entry in load_south_florida_gis_source_catalog(SourceMode.FIXTURE)
        if entry.source_id == "src_broward_bmsd_zoning"
    )
    site = GISSiteContext(
        county=CountyName("Broward"),
        municipality="Hollywood",
        is_unincorporated_or_bmsd=False,
    )

    # When: a BMSD feature is normalized and turned into evidence.
    query = await adapter.query_feature_service(source.source_id, where="1=1", limit=1)
    normalized = await adapter.normalize_feature(source, query.features[0])
    evidence = await adapter.create_evidence(
        source,
        normalized,
        RunId("run_fixture_002"),
        site_context=site,
    )

    # Then: applicability is guarded by the Broward municipal rule.
    assert evidence.applicability is ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION
    assert "BMSD" in evidence.structured_payload["applicability_reason"]


def test_resolve_site_boundary_context_flags_broward_municipal_site() -> None:
    context = resolve_site_boundary_context(
        county=CountyName("Broward"),
        municipality="Hollywood",
        source_mode=SourceMode.FIXTURE,
    )

    assert context["county"] == "Broward"
    assert context["municipality"] == "Hollywood"
    assert context["is_unincorporated_or_bmsd"] is False
    assert context["recommended_zoning_source_ids"] == []
    assert context["controlling_zoning_authority"] == "municipal"
    assert context["controlling_zoning_jurisdiction"] == "Hollywood"
    assert context["zoning_record_applicability"] == "requires_municipal_verification"
    assert "municipal zoning" in str(context["warning"]).lower()


def test_resolve_site_boundary_context_marks_miami_dade_municipal_site_as_direct() -> None:
    context = resolve_site_boundary_context(
        county=CountyName("Miami-Dade"),
        municipality="Miami Gardens",
        source_mode=SourceMode.FIXTURE,
    )

    assert context["county"] == "Miami-Dade"
    assert context["municipality"] == "Miami Gardens"
    assert context["is_unincorporated_or_bmsd"] is False
    assert context["controlling_zoning_authority"] == "municipal"
    assert context["controlling_zoning_jurisdiction"] == "Miami Gardens"
    assert context["zoning_record_applicability"] == "direct"
    assert context["warning"] == ""
    assert "src_miami_dade_municipal_zoning" in context["recommended_zoning_source_ids"]


def test_resolve_site_boundary_context_requires_verification_when_miami_dade_municipality_missing() -> (
    None
):
    context = resolve_site_boundary_context(
        county=CountyName("Miami-Dade"),
        municipality=None,
        source_mode=SourceMode.FIXTURE,
    )

    assert context["county"] == "Miami-Dade"
    assert context["municipality"] is None
    assert context["controlling_zoning_authority"] == "unknown"
    assert context["controlling_zoning_jurisdiction"] == "Miami-Dade"
    assert context["zoning_record_applicability"] == "requires_municipal_verification"
    assert "municipal jurisdiction confirmation" in str(context["warning"]).lower()


def test_query_gis_feature_service_returns_fixture_source_metadata() -> None:
    source = get_gis_source_metadata(
        "src_miami_dade_municipal_zoning",
        source_mode=SourceMode.FIXTURE,
    )
    result = query_gis_feature_service(
        source.source_id,
        where="1=1",
        limit=1,
        source_mode=SourceMode.FIXTURE,
    )

    assert result.provider is GISProvider.MIAMI_DADE_ARCGIS
    assert result.source_id == source.source_id
    assert len(result.features) == 1


@pytest.mark.asyncio
async def test_query_gis_feature_service_async_live_mode_uses_arcgis_response(monkeypatch) -> None:
    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "features": [
                    {
                        "attributes": {"OBJECTID": 9, "ZONE": "T5-O", "MUNICIPALITY": "Miami"},
                        "geometry": {"x": -80.2, "y": 25.8},
                    }
                ]
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict[str, object]) -> _FakeResponse:
            assert "MapServer/2/query" in url
            assert params["where"] == "1=1"
            assert params["resultRecordCount"] == 1
            return _FakeResponse()

    monkeypatch.setattr("plotlot.harness.south_florida_gis_live.httpx.AsyncClient", _FakeClient)

    result = await query_gis_feature_service_async(
        "src_miami_dade_municipal_zoning",
        where="1=1",
        limit=1,
        source_mode=SourceMode.LIVE,
    )

    assert result.provider is GISProvider.MIAMI_DADE_ARCGIS
    assert len(result.features) == 1
    assert result.features[0].attributes["ZONE"] == "T5-O"


@pytest.mark.asyncio
async def test_live_adapter_marks_evidence_freshness_unknown(monkeypatch) -> None:
    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "features": [
                    {
                        "attributes": {"OBJECTID": 5, "ZONE": "T4-R", "MUNICIPALITY": "Miami"},
                        "geometry": {"x": -80.19, "y": 25.77},
                    }
                ]
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict[str, object]) -> _FakeResponse:
            return _FakeResponse()

    monkeypatch.setattr("plotlot.harness.south_florida_gis_live.httpx.AsyncClient", _FakeClient)

    adapter = MiamiDadeGISAdapter(source_mode=SourceMode.LIVE)
    source = get_gis_source_metadata(
        "src_miami_dade_municipal_zoning",
        source_mode=SourceMode.LIVE,
    )

    query = await adapter.query_feature_service(source.source_id, where="1=1", limit=1)
    normalized = await adapter.normalize_feature(source, query.features[0])
    evidence = await adapter.create_evidence(source, normalized, RunId("run_live_001"))

    assert evidence.source_mode is SourceMode.LIVE
    assert evidence.freshness_status is FreshnessStatus.UNKNOWN
