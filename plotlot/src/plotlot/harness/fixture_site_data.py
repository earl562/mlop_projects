from __future__ import annotations

from dataclasses import dataclass

from plotlot.core.types import CompAnalysis, ComparableSale, PropertyRecord
from plotlot.harness.contracts import CountyName


@dataclass(frozen=True, slots=True)
class FixtureSiteProfile:
    key: str
    address: str
    municipality: str
    county: str
    state: str
    lat: float
    lng: float
    folio: str
    zoning_code: str
    zoning_description: str
    lot_size_sqft: float
    lot_dimensions: str
    living_units: int
    assessed_value: float
    market_value: float
    monthly_rent_per_unit: float
    vacancy_pct: float
    operating_expense_pct: float
    cap_rate: float
    max_far: float
    max_units: int
    parking_spaces_per_unit: float
    avg_unit_size_sf: float
    efficiency_factor: float
    hard_costs: float
    soft_costs: float
    contingency: float
    developer_fee: float
    closing_costs: float
    financing_costs: float
    holding_costs: float
    selling_costs: float
    desired_profit: float
    municode_jurisdiction: str
    gis_query: str


_MIAMI_DADE_PROFILE = FixtureSiteProfile(
    key="miami_dade",
    address="example Miami-Dade fixture address",
    municipality="Miami",
    county="Miami-Dade",
    state="FL",
    lat=25.7617,
    lng=-80.1918,
    folio="01-4137-000-0001",
    zoning_code="T4-R",
    zoning_description="General urban residential",
    lot_size_sqft=8_000,
    lot_dimensions="80 x 100",
    living_units=8,
    assessed_value=420_000,
    market_value=515_000,
    monthly_rent_per_unit=2_350,
    vacancy_pct=0.05,
    operating_expense_pct=0.34,
    cap_rate=0.0575,
    max_far=2.0,
    max_units=16,
    parking_spaces_per_unit=1.5,
    avg_unit_size_sf=850,
    efficiency_factor=0.85,
    hard_costs=2_900_000,
    soft_costs=580_000,
    contingency=180_000,
    developer_fee=210_000,
    closing_costs=65_000,
    financing_costs=230_000,
    holding_costs=95_000,
    selling_costs=140_000,
    desired_profit=650_000,
    municode_jurisdiction="miami",
    gis_query="zoning",
)

_BROWARD_PROFILE = FixtureSiteProfile(
    key="broward_bmsd",
    address="example Broward fixture address",
    municipality="BMSD",
    county="Broward",
    state="FL",
    lat=26.1224,
    lng=-80.1373,
    folio="49-4137-000-0001",
    zoning_code="RM-16",
    zoning_description="Residential multifamily district",
    lot_size_sqft=10_500,
    lot_dimensions="105 x 100",
    living_units=10,
    assessed_value=390_000,
    market_value=480_000,
    monthly_rent_per_unit=2_150,
    vacancy_pct=0.055,
    operating_expense_pct=0.35,
    cap_rate=0.06,
    max_far=1.6,
    max_units=14,
    parking_spaces_per_unit=1.5,
    avg_unit_size_sf=875,
    efficiency_factor=0.84,
    hard_costs=2_450_000,
    soft_costs=490_000,
    contingency=160_000,
    developer_fee=180_000,
    closing_costs=55_000,
    financing_costs=205_000,
    holding_costs=82_000,
    selling_costs=120_000,
    desired_profit=540_000,
    municode_jurisdiction="broward",
    gis_query="zoning",
)

_MIAMI_GARDENS_45_PROFILE = FixtureSiteProfile(
    key="miami_gardens_45_nw_209",
    address="45 NW 209 ST",
    municipality="Miami Gardens",
    county="Miami-Dade",
    state="FL",
    lat=25.967404,
    lng=-80.202576,
    folio="3411360031910",
    zoning_code="R-1",
    zoning_description="Single-family detached residential",
    lot_size_sqft=10_105,
    lot_dimensions="96.24 x 105",
    living_units=1,
    assessed_value=80_000,
    market_value=120_000,
    monthly_rent_per_unit=3_100,
    vacancy_pct=0.05,
    operating_expense_pct=0.34,
    cap_rate=0.0625,
    max_far=0.5,
    max_units=1,
    parking_spaces_per_unit=2.0,
    avg_unit_size_sf=2_100,
    efficiency_factor=0.88,
    hard_costs=315_000,
    soft_costs=63_000,
    contingency=31_500,
    developer_fee=25_000,
    closing_costs=12_000,
    financing_costs=24_000,
    holding_costs=12_000,
    selling_costs=30_000,
    desired_profit=85_000,
    municode_jurisdiction="miami_gardens",
    gis_query="R-1 Miami Gardens zoning",
)

_DEFAULT_PROFILE = _MIAMI_DADE_PROFILE


def fixture_site_profile_for_address(address: str) -> FixtureSiteProfile:
    lowered = address.casefold()
    if "45 nw 209" in lowered:
        return _MIAMI_GARDENS_45_PROFILE
    if "broward" in lowered:
        return _BROWARD_PROFILE
    if "miami-dade" in lowered or "miami" in lowered:
        return _MIAMI_DADE_PROFILE
    return _DEFAULT_PROFILE


def is_known_fixture_address(address: str) -> bool:
    lowered = address.casefold()
    return any(
        token in lowered
        for token in (
            "fixture address",
            "45 nw 209",
            "broward fixture",
            "miami-dade fixture",
            "miami fixture",
        )
    )


def fixture_property_record(profile: FixtureSiteProfile) -> PropertyRecord:
    return PropertyRecord(
        folio=profile.folio,
        address=profile.address,
        municipality=profile.municipality,
        county=profile.county,
        zoning_code=profile.zoning_code,
        zoning_description=profile.zoning_description,
        lot_size_sqft=profile.lot_size_sqft,
        lot_dimensions=profile.lot_dimensions,
        living_units=profile.living_units,
        assessed_value=profile.assessed_value,
        market_value=profile.market_value,
        lat=profile.lat,
        lng=profile.lng,
        zoning_layer_url=f"https://fixtures.plotlot.local/{profile.key}/zoning",
    )


def fixture_comp_analysis(profile: FixtureSiteProfile) -> CompAnalysis:
    if profile.key == "miami_gardens_45_nw_209":
        comparables = [
            ComparableSale(
                address="17605 NW 19th Avenue, Miami Gardens, FL 33056",
                sale_price=135_000,
                sale_date="2025-12-01",
                lot_size_sqft=9_000,
                zoning_code="R-1",
                distance_miles=4.2,
                price_per_acre=653_400.0,
            ),
            ComparableSale(
                address="2940 NW 169th Ter, Miami Gardens, FL 33056",
                sale_price=145_000,
                sale_date="2025-10-10",
                lot_size_sqft=10_000,
                zoning_code="R-1",
                distance_miles=4.8,
                price_per_acre=631_620.0,
            ),
            ComparableSale(
                address="168 Terrace, Miami Gardens, FL 33056",
                sale_price=120_000,
                sale_date="2025-08-15",
                lot_size_sqft=7_500,
                zoning_code="R-1",
                distance_miles=4.9,
                price_per_acre=696_960.0,
            ),
        ]
        unit_comps = [
            ComparableSale(
                address="105 NE 213th St, Miami Gardens, FL 33179",
                sale_price=699_000,
                sale_date="2026-01-20",
                lot_size_sqft=8_250,
                zoning_code="R-1",
                distance_miles=1.0,
                price_per_unit=699_000.0,
            ),
            ComparableSale(
                address="115 NE 213th St, Miami Gardens, FL 33179",
                sale_price=500_000,
                sale_date="2025-11-05",
                lot_size_sqft=8_250,
                zoning_code="R-1",
                distance_miles=1.0,
                price_per_unit=500_000.0,
            ),
            ComparableSale(
                address="100 NW 208th St, Miami Gardens, FL 33169",
                sale_price=500_000,
                sale_date="2025-09-12",
                lot_size_sqft=7_500,
                zoning_code="R-1",
                distance_miles=0.4,
                price_per_unit=500_000.0,
            ),
        ]
    elif profile.key == "broward_bmsd":
        comparables = [
            ComparableSale(
                address="101 Broward Land Ln",
                sale_price=275_000,
                sale_date="2026-02-14",
                lot_size_sqft=10_200,
                zoning_code="RM-16",
                distance_miles=0.6,
                price_per_acre=1_173_529.41,
            ),
            ComparableSale(
                address="205 Broward Land Ln",
                sale_price=295_000,
                sale_date="2026-03-20",
                lot_size_sqft=10_800,
                zoning_code="RM-16",
                distance_miles=0.9,
                price_per_acre=1_189_629.63,
            ),
        ]
        unit_comps = [
            ComparableSale(
                address="303 Broward Built Ave",
                sale_price=1_980_000,
                sale_date="2026-01-30",
                lot_size_sqft=12_000,
                zoning_code="RM-16",
                distance_miles=1.1,
                price_per_unit=198_000.0,
            ),
            ComparableSale(
                address="411 Broward Built Ave",
                sale_price=2_240_000,
                sale_date="2025-12-15",
                lot_size_sqft=14_000,
                zoning_code="RM-16",
                distance_miles=1.4,
                price_per_unit=203_636.36,
            ),
        ]
    else:
        comparables = [
            ComparableSale(
                address="100 Miami Land Ave",
                sale_price=315_000,
                sale_date="2026-03-15",
                lot_size_sqft=8_100,
                zoning_code="T4-R",
                distance_miles=0.4,
                price_per_acre=1_692_000.0,
            ),
            ComparableSale(
                address="220 Miami Land Ave",
                sale_price=330_000,
                sale_date="2026-01-11",
                lot_size_sqft=8_250,
                zoning_code="T4-R",
                distance_miles=0.7,
                price_per_acre=1_742_400.0,
            ),
        ]
        unit_comps = [
            ComparableSale(
                address="350 Miami Built Blvd",
                sale_price=2_520_000,
                sale_date="2026-02-10",
                lot_size_sqft=9_500,
                zoning_code="T4-R",
                distance_miles=0.9,
                price_per_unit=252_000.0,
            ),
            ComparableSale(
                address="480 Miami Built Blvd",
                sale_price=2_640_000,
                sale_date="2025-11-22",
                lot_size_sqft=10_000,
                zoning_code="T4-R",
                distance_miles=1.2,
                price_per_unit=240_000.0,
            ),
        ]

    median_land = sum(comp.price_per_acre for comp in comparables) / len(comparables)
    subject_acres = profile.lot_size_sqft / 43_560
    adv_values = [comp.price_per_unit or 0.0 for comp in unit_comps]
    low_land = min(comp.price_per_acre for comp in comparables)
    high_land = max(comp.price_per_acre for comp in comparables)
    low_adv = min(adv_values)
    high_adv = max(adv_values)
    return CompAnalysis(
        comparables=comparables,
        median_price_per_acre=round(median_land, 2),
        estimated_land_value=round(subject_acres * median_land, 2),
        price_per_acre_low=round(low_land, 2),
        price_per_acre_high=round(high_land, 2),
        estimated_land_value_low=round(subject_acres * low_land, 2),
        estimated_land_value_high=round(subject_acres * high_land, 2),
        adv_per_unit=round(sum(adv_values) / len(adv_values), 2),
        adv_per_unit_low=round(low_adv, 2),
        adv_per_unit_high=round(high_adv, 2),
        adv_source="fixture_comps",
        unit_comparables=unit_comps,
        confidence=0.78,
        notes=[
            "Fixture comps synthesized from county-style sale records for harness regression coverage."
        ],
    )


def fixture_county_name(profile: FixtureSiteProfile) -> CountyName:
    return CountyName(profile.county)
