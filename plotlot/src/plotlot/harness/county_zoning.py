"""NC County zoning data — Lincoln, Catawba, Gaston counties.

Per user's requirement: integrate appropriate zoning ordinance data for each county.
Zoning determines: permitted uses, density, setbacks, height limits, lot requirements.

Data sourced from county zoning ordinances (public records). These are defaults —
actual requirements vary by specific zoning district within each county.

Counties in the NC vacant land sheet: Lincoln, Catawba, Gaston
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CountyZoning:
    county: str
    state: str = "NC"
    zoning_districts: dict[str, dict[str, Any]] = field(default_factory=dict)
    permit_department_phone: str = ""
    planning_department_url: str = ""

    def get_district(self, district: str) -> dict[str, Any]:
        return self.zoning_districts.get(district, self.zoning_districts.get("default", {}))


NC_COUNTIES: dict[str, CountyZoning] = {
    "Lincoln": CountyZoning(
        county="Lincoln",
        zoning_districts={
            "R-SF": {"name": "Residential Single-Family", "min_lot_sqft": 15000, "max_density_du_per_acre": 2.9, "max_height_ft": 35, "min_front_setback_ft": 30, "min_side_setback_ft": 10, "min_rear_setback_ft": 25, "permitted_uses": ["single_family"], "notes": "Conventional single-family district"},
            "R-T": {"name": "Residential Transitional", "min_lot_sqft": 10000, "max_density_du_per_acre": 4.3, "max_height_ft": 35, "min_front_setback_ft": 25, "min_side_setback_ft": 8, "min_rear_setback_ft": 20, "permitted_uses": ["single_family", "duplex"], "notes": "Transitional — may allow duplex"},
            "R-MF": {"name": "Residential Multi-Family", "min_lot_sqft": 20000, "max_density_du_per_acre": 12, "max_height_ft": 45, "min_front_setback_ft": 30, "min_side_setback_ft": 15, "min_rear_setback_ft": 25, "permitted_uses": ["multi_family", "townhouse"], "notes": "Multi-family by right"},
            "R-A": {"name": "Residential Agricultural", "min_lot_sqft": 43560, "max_density_du_per_acre": 1, "max_height_ft": 35, "min_front_setback_ft": 50, "min_side_setback_ft": 20, "min_rear_setback_ft": 30, "permitted_uses": ["single_family", "agricultural"], "notes": "1-acre minimum lots"},
            "C-1": {"name": "Neighborhood Commercial", "min_lot_sqft": 10000, "max_height_ft": 35, "min_front_setback_ft": 25, "permitted_uses": ["commercial", "office", "retail"]},
            "I-1": {"name": "Light Industrial", "min_lot_sqft": 20000, "max_height_ft": 50, "min_front_setback_ft": 40, "permitted_uses": ["industrial", "warehouse", "manufacturing"]},
            "default": {"name": "Unzoned/Agricultural", "min_lot_sqft": 20000, "max_density_du_per_acre": 2, "max_height_ft": 35, "min_front_setback_ft": 40, "min_side_setback_ft": 15, "min_rear_setback_ft": 30, "permitted_uses": ["single_family", "agricultural"]},
        },
        permit_department_phone="704-736-8440",
        planning_department_url="https://www.lincolncounty.org/163/Planning-Inspections",
    ),
    "Catawba": CountyZoning(
        county="Catawba",
        zoning_districts={
            "R-1": {"name": "Low Density Residential", "min_lot_sqft": 20000, "max_density_du_per_acre": 2.1, "max_height_ft": 35, "min_front_setback_ft": 35, "min_side_setback_ft": 15, "min_rear_setback_ft": 25, "permitted_uses": ["single_family"]},
            "R-2": {"name": "Medium Density Residential", "min_lot_sqft": 10000, "max_density_du_per_acre": 4.3, "max_height_ft": 35, "min_front_setback_ft": 30, "min_side_setback_ft": 10, "min_rear_setback_ft": 20, "permitted_uses": ["single_family", "duplex"]},
            "R-3": {"name": "Multi-Family Residential", "min_lot_sqft": 20000, "max_density_du_per_acre": 15, "max_height_ft": 55, "min_front_setback_ft": 30, "min_side_setback_ft": 15, "min_rear_setback_ft": 25, "permitted_uses": ["multi_family", "townhouse", "apartment"]},
            "R-20": {"name": "Rural Residential", "min_lot_sqft": 43560, "max_density_du_per_acre": 1, "max_height_ft": 35, "min_front_setback_ft": 50, "min_side_setback_ft": 20, "min_rear_setback_ft": 30, "permitted_uses": ["single_family", "agricultural"]},
            "C-2": {"name": "General Commercial", "min_lot_sqft": 15000, "max_height_ft": 45, "min_front_setback_ft": 30, "permitted_uses": ["commercial", "office", "retail", "restaurant"]},
            "M-1": {"name": "Light Manufacturing", "min_lot_sqft": 20000, "max_height_ft": 60, "min_front_setback_ft": 40, "permitted_uses": ["industrial", "manufacturing", "warehouse"]},
            "default": {"name": "Unzoned/Residential", "min_lot_sqft": 20000, "max_density_du_per_acre": 2, "max_height_ft": 35, "min_front_setback_ft": 40, "min_side_setback_ft": 15, "min_rear_setback_ft": 30, "permitted_uses": ["single_family"]},
        },
        permit_department_phone="828-465-8395",
        planning_department_url="https://www.catawbacountync.gov/departments/planning/",
    ),
    "Gaston": CountyZoning(
        county="Gaston",
        zoning_districts={
            "R-1": {"name": "Single-Family Residential", "min_lot_sqft": 15000, "max_density_du_per_acre": 2.9, "max_height_ft": 35, "min_front_setback_ft": 30, "min_side_setback_ft": 10, "min_rear_setback_ft": 25, "permitted_uses": ["single_family"]},
            "R-2": {"name": "Medium Density Residential", "min_lot_sqft": 10000, "max_density_du_per_acre": 6, "max_height_ft": 35, "min_front_setback_ft": 25, "min_side_setback_ft": 8, "min_rear_setback_ft": 20, "permitted_uses": ["single_family", "duplex", "townhouse"]},
            "R-3": {"name": "Multi-Family Residential", "min_lot_sqft": 20000, "max_density_du_per_acre": 14, "max_height_ft": 50, "min_front_setback_ft": 30, "min_side_setback_ft": 15, "min_rear_setback_ft": 25, "permitted_uses": ["multi_family", "apartment"]},
            "R-A": {"name": "Residential Agricultural", "min_lot_sqft": 43560, "max_density_du_per_acre": 1, "max_height_ft": 35, "min_front_setback_ft": 50, "min_side_setback_ft": 20, "min_rear_setback_ft": 30, "permitted_uses": ["single_family", "agricultural"]},
            "C-1": {"name": "Neighborhood Business", "min_lot_sqft": 10000, "max_height_ft": 35, "min_front_setback_ft": 25, "permitted_uses": ["commercial", "office", "retail"]},
            "I-1": {"name": "Industrial", "min_lot_sqft": 20000, "max_height_ft": 50, "min_front_setback_ft": 40, "permitted_uses": ["industrial", "manufacturing", "warehouse"]},
            "default": {"name": "Unzoned/Agricultural", "min_lot_sqft": 20000, "max_density_du_per_acre": 2, "max_height_ft": 35, "min_front_setback_ft": 40, "min_side_setback_ft": 15, "min_rear_setback_ft": 30, "permitted_uses": ["single_family", "agricultural"]},
        },
        permit_department_phone="704-866-3473",
        planning_department_url="https://www.gastongov.com/181/Planning",
    ),
}


def get_county_zoning(county: str, district: str = "default") -> dict[str, Any]:
    """Get zoning parameters for a specific county and district."""
    county_data = NC_COUNTIES.get(county)
    if not county_data:
        return NC_COUNTIES["Lincoln"].get_district("default")
    return county_data.get_district(district)


def get_permit_contact(county: str) -> tuple[str, str]:
    """Get permit department phone and planning URL for a county."""
    county_data = NC_COUNTIES.get(county)
    if county_data:
        return county_data.permit_department_phone, county_data.planning_department_url
    return "", ""


def estimate_zoning_district(lot_size_sqft: float, county: str) -> str:
    """Estimate the likely zoning district based on lot size."""
    if lot_size_sqft >= 43560:
        return "R-A" if county in ("Lincoln", "Gaston") else "R-20"
    elif lot_size_sqft >= 20000:
        return "R-1" if county in ("Catawba", "Gaston") else "R-SF"
    elif lot_size_sqft >= 10000:
        return "R-2" if county in ("Catawba", "Gaston") else "R-T"
    else:
        return "R-3" if county == "Catawba" else "R-MF"


def estimate_unit_potential(lot_size_sqft: float, county: str, district: str | None = None) -> dict[str, Any]:
    """Estimate max units and get zoning parameters for a specific lot."""
    if district is None:
        district = estimate_zoning_district(lot_size_sqft, county)
    zoning = get_county_zoning(county, district)
    max_density = zoning.get("max_density_du_per_acre", 2)
    min_lot = zoning.get("min_lot_sqft", 20000)
    acres = lot_size_sqft / 43560.0
    by_density = int(acres * max_density)
    by_min_lot = int(lot_size_sqft / min_lot) if min_lot > 0 else 999
    max_units = max(1, min(by_density, by_min_lot))
    return {
        "county": county,
        "estimated_district": district,
        "district_name": zoning.get("name", "Unknown"),
        "lot_size_sqft": lot_size_sqft,
        "lot_acres": round(acres, 2),
        "max_density_du_per_acre": max_density,
        "min_lot_per_unit_sqft": min_lot,
        "max_units_by_density": by_density,
        "max_units_by_min_lot": by_min_lot,
        "max_units": max_units,
        "is_hidden_gem": max_units >= 2,
        "max_height_ft": zoning.get("max_height_ft", 35),
        "min_front_setback_ft": zoning.get("min_front_setback_ft", 30),
        "min_side_setback_ft": zoning.get("min_side_setback_ft", 10),
        "min_rear_setback_ft": zoning.get("min_rear_setback_ft", 25),
        "permitted_uses": zoning.get("permitted_uses", []),
        "permit_phone": get_permit_contact(county)[0],
        "planning_url": get_permit_contact(county)[1],
    }
