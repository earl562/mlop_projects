"""Mecklenburg County (Charlotte NC metro) property provider.

Uses the Mecklenburg County GIS REST API for property lookups.
Covers: Charlotte, Huntersville, Cornelius, Davidson, Matthews, Mint Hill,
Pineville, and other Charlotte metro municipalities within Mecklenburg County.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from typing import Annotated

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from plotlot.core.types import PropertyRecord
from plotlot.property.base import PropertyProvider

logger = logging.getLogger(__name__)

MECKLENBURG_PARCEL_URL = "https://meckgis.mecklenburgcountync.gov/server/rest/services/TaxParcel_camadata/FeatureServer/0/query"
MECKLENBURG_OWNERSHIP_URL = "https://meckgis.mecklenburgcountync.gov/server/rest/services/TaxParcel_Camaownershipvalues/FeatureServer/0/query"
MECKLENBURG_ZONING_URL = "https://meckgis.mecklenburgcountync.gov/server/rest/services/ParcelsZoningZipcode/FeatureServer/0/query"
PARCEL_FIELDS = (
    "pid,parcelid,address,loccity,legalacres,gisacres,totalvalue,totmarkval,"
    "lusecode,landuse_description,heatedarea,yearbuilt,ownrlstnme,ownrfrstnme"
)
NonNegativeNumber = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class _Attributes(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    pid: str = Field(min_length=1)
    parcelid: str = ""
    camapid: str = ""
    address: str | None = None
    loccity: str | None = None
    municipality_desc: str | None = None
    situsaddress1: str | None = None
    legalacres: NonNegativeNumber | None = None
    gisacres: NonNegativeNumber | None = None
    totalvalue: NonNegativeNumber | None = None
    totmarkval: NonNegativeNumber | None = None
    heatedarea: NonNegativeNumber | None = None
    yearbuilt: Annotated[int, Field(ge=0)] | None = None
    lusecode: str | None = None
    landuse_description: str | None = None
    ownrlstnme: str | None = None
    ownrfrstnme: str | None = None
    zone_class: str | None = None


class _Feature(BaseModel):
    model_config = ConfigDict(frozen=True)
    attributes: _Attributes


class _ArcGISError(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: int


class _Response(BaseModel):
    model_config = ConfigDict(frozen=True)
    features: tuple[_Feature, ...] | None = None
    error: _ArcGISError | None = None
    exceededTransferLimit: bool = False


def _normalize(value: str) -> str:
    return " ".join(value.upper().replace(".", "").split())


def _matches_address(attributes: _Attributes, address: str) -> bool:
    candidate = _normalize(attributes.address or "")
    city = _normalize(attributes.loccity or "")
    parts = [_normalize(part) for part in address.split(",")]
    requested_city = re.sub(r"\bNC\b.*$", "", parts[1]).strip() if len(parts) > 1 else ""
    if requested_city and requested_city != city:
        return False
    without_zip = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", candidate)
    street = without_zip.removesuffix(f" {city} NC") if city else without_zip
    return bool(parts[0]) and parts[0] in {candidate, without_zip, street}


async def _query(
    client: httpx.AsyncClient, url: str, params: dict[str, str]
) -> tuple[_Attributes, ...] | None:
    try:
        response = await client.get(
            url,
            params={
                "f": "json",
                "returnGeometry": "false",
                "resultRecordCount": "21",
                **params,
            },
        )
        response.raise_for_status()
        data = _Response.model_validate_json(response.content)
    except (httpx.HTTPError, ValidationError) as exc:
        logger.warning(
            "Mecklenburg source unavailable source=%s error_type=%s", url, type(exc).__name__
        )
        return None
    if data.error or data.features is None or data.exceededTransferLimit or len(data.features) > 20:
        logger.warning("Mecklenburg source incomplete source=%s", url)
        return None
    return tuple(feature.attributes for feature in data.features)


class MecklenburgProvider(PropertyProvider):
    """Property lookup for Mecklenburg County, NC."""

    county = "mecklenburg"

    async def lookup(
        self,
        address: str,
        county: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        state: str = "",
    ) -> PropertyRecord | None:
        """Resolve a unique current tax parcel before attaching county zoning."""
        if county.strip().lower().removesuffix(" county") != self.county or state.upper() not in {
            "",
            "NC",
        }:
            return None
        street = _normalize(address.split(",")[0])
        if not re.match(r"^\d+\s+\S", street) or any(char in street for char in "%_"):
            return None
        if (lat is None) != (lng is None):
            return None
        if (
            lat is not None
            and lng is not None
            and not (
                math.isfinite(lat)
                and math.isfinite(lng)
                and -90 <= lat <= 90
                and -180 <= lng <= 180
            )
        ):
            return None
        try:
            async with asyncio.timeout(20), httpx.AsyncClient(timeout=15.0) as client:
                candidates: tuple[_Attributes, ...] | None = ()
                if lat is not None and lng is not None:
                    candidates = await _query(
                        client,
                        MECKLENBURG_PARCEL_URL,
                        {
                            "geometry": f"{lng},{lat}",
                            "geometryType": "esriGeometryPoint",
                            "inSR": "4326",
                            "spatialRel": "esriSpatialRelIntersects",
                            "outFields": PARCEL_FIELDS,
                        },
                    )
                if candidates is None:
                    return None
                if not candidates:
                    escaped = street.replace("'", "''")
                    candidates = await _query(
                        client,
                        MECKLENBURG_PARCEL_URL,
                        {
                            "where": f"UPPER(address) = '{escaped}' OR UPPER(address) LIKE '{escaped} %'",
                            "outFields": PARCEL_FIELDS,
                        },
                    )
                if candidates is None:
                    return None
                matches = [item for item in candidates if _matches_address(item, address)]
                if len(matches) != 1 or matches[0].pid != matches[0].parcelid:
                    logger.warning("Mecklenburg parcel identity unresolved")
                    return None
                parcel = matches[0]
                escaped_pid = parcel.pid.replace("'", "''")
                parcel_filter = f"pid = '{escaped_pid}'"
                owners = await _query(
                    client,
                    MECKLENBURG_OWNERSHIP_URL,
                    {
                        "where": parcel_filter,
                        "outFields": "pid,camapid,municipality_desc,situsaddress1",
                    },
                )
                if owners is None or len(owners) != 1:
                    return None
                owner = owners[0]
                if (
                    owner.pid != parcel.pid
                    or owner.camapid != parcel.parcelid
                    or not owner.municipality_desc
                    or _normalize(owner.situsaddress1 or "") != _normalize(parcel.address or "")
                ):
                    logger.warning("Mecklenburg tax identity or jurisdiction unresolved")
                    return None
                record = self._parse_feature(parcel)
                record.municipality = owner.municipality_desc
                zones = await _query(
                    client,
                    MECKLENBURG_ZONING_URL,
                    {
                        "where": parcel_filter,
                        "outFields": "pid,zone_class",
                    },
                )
                if zones and all(zone.pid == parcel.pid and zone.zone_class for zone in zones):
                    codes = {zone.zone_class for zone in zones}
                    if len(codes) == 1:
                        record.zoning_code = zones[0].zone_class or ""
                return record
        except TimeoutError:
            logger.warning("Mecklenburg lookup deadline exceeded")
            return None

    def _parse_feature(self, attrs: _Attributes) -> PropertyRecord:
        legal_acres = attrs.legalacres or 0
        gis_acres = attrs.gisacres or 0
        lot_size = (legal_acres or gis_acres) * 43560
        return PropertyRecord(
            folio=attrs.parcelid,
            address=attrs.address or "",
            county="Mecklenburg",
            owner=" ".join(part for part in (attrs.ownrfrstnme, attrs.ownrlstnme) if part),
            land_use_code=attrs.lusecode or "",
            land_use_description=attrs.landuse_description or "",
            lot_size_sqft=lot_size,
            lot_size_source="assessor" if legal_acres else "geometry" if gis_acres else "",
            assessed_value=attrs.totalvalue or 0,
            market_value=attrs.totmarkval or 0,
            year_built=attrs.yearbuilt or 0,
            building_area_sqft=attrs.heatedarea or 0,
        )
