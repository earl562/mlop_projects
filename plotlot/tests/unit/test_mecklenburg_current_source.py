from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from pydantic import JsonValue

from plotlot.core.types import PropertyRecord
from plotlot.property.mecklenburg import MecklenburgProvider

PARCEL_URL = "https://meckgis.mecklenburgcountync.gov/server/rest/services/TaxParcel_camadata/FeatureServer/0/query"
ZONING_URL = "https://meckgis.mecklenburgcountync.gov/server/rest/services/ParcelsZoningZipcode/FeatureServer/0/query"
OWNERSHIP_URL = "https://meckgis.mecklenburgcountync.gov/server/rest/services/TaxParcel_Camaownershipvalues/FeatureServer/0/query"
ADDRESS = "600 E 4TH ST, Charlotte, NC"
PARCEL: dict[str, JsonValue] = {
    "pid": "12502601",
    "parcelid": "12502601",
    "address": "600 E 4TH ST CHARLOTTE NC",
    "loccity": "CHARLOTTE",
    "legalacres": 0.0,
    "gisacres": 2.67200098,
    "totalac": 116130.0,
    "landunit": "SQUARE FEET",
    "lusecode": "O400",
    "landuse_description": "OFFICE",
    "totalvalue": 87383800,
    "totmarkval": 87383800,
    "heatedarea": 386012.0,
    "yearbuilt": 1986,
}


async def _lookup(
    payload: dict[str, JsonValue],
    zoning: dict[str, JsonValue] | None = None,
    ownership: dict[str, JsonValue] | None = None,
) -> tuple[PropertyRecord | None, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url).startswith(OWNERSHIP_URL):
            return httpx.Response(
                200,
                json=ownership
                if ownership is not None
                else {
                    "features": [
                        {
                            "attributes": {
                                "pid": "12502601",
                                "camapid": "12502601",
                                "municipality_desc": "CHARLOTTE",
                                "situsaddress1": "600 E 4TH ST CHARLOTTE NC",
                            }
                        }
                    ]
                },
            )
        if str(request.url).startswith(ZONING_URL):
            return httpx.Response(
                200,
                json=zoning
                if zoning is not None
                else {"features": [{"attributes": {"pid": "12502601", "zone_class": "UC"}}]},
            )
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("plotlot.property.mecklenburg.httpx.AsyncClient", return_value=client):
        record = await MecklenburgProvider().lookup(ADDRESS, "Mecklenburg", state="NC")
    return record, requests


async def test_current_county_schema_preserves_identity_and_explicit_area_provenance() -> None:
    # Given the owner-free fields observed for the county's government-center parcel.
    payload: dict[str, JsonValue] = {"features": [{"attributes": PARCEL}]}
    # When the real provider interprets the current county response.
    record, requests = await _lookup(payload)
    # Then current fields are mapped without guessing area units or mailing jurisdiction.
    assert record is not None
    assert (record.folio, record.address, record.municipality) == (
        "12502601",
        "600 E 4TH ST CHARLOTTE NC",
        "CHARLOTTE",
    )
    assert record.zoning_code == "UC"
    assert record.lot_size_sqft == pytest.approx(2.67200098 * 43560)
    assert record.lot_size_source == "geometry"
    assert (record.year_built, record.building_area_sqft) == (1986, 386012.0)
    assert (record.land_use_code, record.assessed_value) == ("O400", 87383800)
    assert [str(request.url).split("?")[0] for request in requests] == [
        PARCEL_URL,
        OWNERSHIP_URL,
        ZONING_URL,
    ]


@pytest.mark.parametrize("acres", [0.01, 2.0, 50001.0])
async def test_legal_acres_use_one_conversion_at_every_magnitude(acres: float) -> None:
    # Given explicit assessor legal acres and an unrelated GIS area.
    payload: dict[str, JsonValue] = {
        "features": [{"attributes": {**PARCEL, "legalacres": acres, "gisacres": 100.0}}]
    }
    # When the provider parses the parcel.
    record, _ = await _lookup(payload)
    # Then the acreage unit, not the value's magnitude, determines conversion.
    assert record is not None
    assert record.lot_size_sqft == pytest.approx(acres * 43560)
    assert record.lot_size_source == "assessor"


@pytest.mark.parametrize(
    "replacement",
    [
        {"address": "600 E 24TH ST CHARLOTTE NC"},
        {"address": "600 E 4TH ST HUNTERSVILLE NC", "loccity": "HUNTERSVILLE"},
        {"parcelid": "12502699"},
        {"pid": ""},
        {"heatedarea": "not-a-number"},
    ],
)
async def test_conflicting_or_invalid_parcel_does_not_become_subject(
    replacement: dict[str, JsonValue],
) -> None:
    # Given a candidate whose address, identity or typed data conflicts.
    payload: dict[str, JsonValue] = {"features": [{"attributes": {**PARCEL, **replacement}}]}
    # When lookup sees the response.
    record, requests = await _lookup(payload)
    # Then it abstains before querying zoning for the wrong or malformed parcel.
    assert record is None
    assert len(requests) == 1


@pytest.mark.parametrize("truncated", [False, True], ids=["ambiguous", "truncated"])
async def test_multiple_or_incomplete_parcel_response_does_not_choose_first(
    truncated: bool,
) -> None:
    # Given two matching tax records, or a server-truncated candidate set.
    features: list[JsonValue] = [{"attributes": PARCEL}]
    if not truncated:
        features.append({"attributes": {**PARCEL, "pid": "12502699", "parcelid": "12502699"}})
    payload: dict[str, JsonValue] = {"features": features, "exceededTransferLimit": truncated}
    # When lookup receives that ambiguous inventory.
    record, _ = await _lookup(payload)
    # Then no arbitrary first record is promoted.
    assert record is None


async def test_arcgis_error_envelope_is_not_a_successful_feature_response() -> None:
    # Given HTTP 200 with the actual ArcGIS error envelope and misleading features.
    payload: dict[str, JsonValue] = {
        "error": {"code": 404, "message": "Service not found"},
        "features": [{"attributes": PARCEL}],
    }
    # When the provider parses the source result.
    record, _ = await _lookup(payload)
    # Then transport success cannot conceal a failed data source.
    assert record is None


@pytest.mark.parametrize(
    "zoning",
    [
        {"features": [{"attributes": {"pid": "other", "zone_class": "UC"}}]},
        {
            "features": [
                {"attributes": {"pid": "12502601", "zone_class": "UC"}},
                {"attributes": {"pid": "12502601", "zone_class": "N1-A"}},
            ]
        },
        {
            "features": [{"attributes": {"pid": "12502601", "zone_class": "UC"}}],
            "exceededTransferLimit": True,
        },
        {"error": {"code": 503, "message": "Unavailable"}},
    ],
)
async def test_ambiguous_zoning_preserves_parcel_but_withholds_zone(
    zoning: dict[str, JsonValue],
) -> None:
    # Given a valid parcel with missing, mismatched or incomplete zoning evidence.
    payload: dict[str, JsonValue] = {"features": [{"attributes": PARCEL}]}
    # When the provider obtains the independently queried zoning response.
    record, _ = await _lookup(payload, zoning)
    # Then property identity survives but no unsupported zone is reported.
    assert record is not None
    assert record.folio == "12502601"
    assert record.zoning_code == ""


@pytest.mark.parametrize("tax_id", ["other", "12502601"])
async def test_tax_identity_and_jurisdiction_must_be_confirmed(tax_id: str) -> None:
    # Given a mismatched tax ID or a missing jurisdiction, despite a matching parcel shape.
    ownership: dict[str, JsonValue] = {
        "features": [
            {
                "attributes": {
                    "pid": "12502601",
                    "camapid": tax_id,
                    "municipality_desc": "CHARLOTTE" if tax_id == "other" else "",
                    "situsaddress1": "600 E 4TH ST CHARLOTTE NC",
                }
            }
        ]
    }
    # When the provider reconciles its CAMA result with the ownership source.
    record, _ = await _lookup({"features": [{"attributes": PARCEL}]}, ownership=ownership)
    # Then a postal city cannot silently supply the missing jurisdiction.
    assert record is None
