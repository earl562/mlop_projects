"""Open-data/geospatial service wrappers returning cited layer candidates."""

from __future__ import annotations

from typing import cast

from pydantic import HttpUrl

from plotlot.land_use.citations import arcgis_layer_citation
from plotlot.land_use.models import EvidenceConfidence, LayerCandidate, LayerType
from plotlot.property.hub_discovery import discover_datasets


async def discover_layers(*, county: str, state: str, lat: float, lng: float):
    parcels, zoning = await discover_datasets(county=county, state=state, lat=lat, lng=lng)

    candidates: list[LayerCandidate] = []
    for ds in [parcels, zoning]:
        if not ds:
            continue
        citation = arcgis_layer_citation(
            title=ds.name,
            service_url=f"{ds.url}/{ds.layer_id}" if ds.layer_id is not None else ds.url,
            jurisdiction=f"{county}, {state}",
            raw_text_for_hash=f"{ds.dataset_id}:{ds.url}:{ds.layer_id}:{','.join(ds.fields)}",
        )
        candidates.append(
            LayerCandidate(
                id=ds.dataset_id,
                title=ds.name,
                source_url=HttpUrl(ds.url),
                service_url=HttpUrl(ds.url),
                layer_id=ds.layer_id or 0,
                layer_type=cast(LayerType, ds.dataset_type),
                field_mapping_confidence=EvidenceConfidence.MEDIUM,
                citation=citation,
            )
        )
    return candidates
