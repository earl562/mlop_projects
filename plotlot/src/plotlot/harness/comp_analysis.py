"""Comparable sales analysis — land comps + new construction comps.

Per user's workflow:
1. Land comps: similar vacant lots sold in 1-3 mile radius (max 5 miles)
2. New build comps: houses built in last 6-12 months — what land cost + what house sold for
3. Formula: (New construction sale × 15%) - $15K = Offer

Data source: NC county tax assessor records + our lead dataset.
Structured for GIS/API integration when available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class LandComp:
    address: str
    county: str
    sale_date: str = ""
    sale_price: float = 0.0
    lot_size_sqft: float = 0.0
    lot_acres: float = 0.0
    price_per_acre: float = 0.0
    price_per_sqft: float = 0.0
    distance_miles: float = 0.0
    zoning: str = ""
    source: str = "tax_assessor"


@dataclass  
class NewBuildComp:
    address: str
    county: str
    build_year: int = 0
    land_cost: float = 0.0
    construction_cost: float = 0.0
    sale_price: float = 0.0
    sale_date: str = ""
    sqft: float = 0.0
    price_per_sqft: float = 0.0
    bedrooms: int = 0
    bathrooms: int = 0
    lot_acres: float = 0.0
    days_on_market: int = 0
    source: str = "tax_assessor"


@dataclass
class CompAnalysis:
    land_comps: list[LandComp] = field(default_factory=list)
    new_build_comps: list[NewBuildComp] = field(default_factory=list)
    avg_land_price_per_acre: float = 0.0
    avg_land_price_per_sqft: float = 0.0
    avg_new_build_price_per_sqft: float = 0.0
    avg_new_build_sale_price: float = 0.0
    avg_new_build_land_cost: float = 0.0
    estimated_build_value: float = 0.0
    suggested_offer: float = 0.0
    comp_count_land: int = 0
    comp_count_new_build: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "land_comps_count": self.comp_count_land,
            "new_build_comps_count": self.comp_count_new_build,
            "avg_land_per_acre": round(self.avg_land_price_per_acre, 2),
            "avg_land_per_sqft": round(self.avg_land_price_per_sqft, 4),
            "avg_new_build_price": round(self.avg_new_build_sale_price, 2),
            "avg_new_build_ppsf": round(self.avg_new_build_price_per_sqft, 2),
            "avg_new_build_land_cost": round(self.avg_new_build_land_cost, 2),
            "estimated_build_value": round(self.estimated_build_value, 2),
            "suggested_offer": round(self.suggested_offer, 2),
        }


class CompAnalyzer:
    """Find and analyze comparable sales for land acquisition."""

    def __init__(self, all_leads: list[dict[str, Any]]):
        self._all_leads = all_leads

    def analyze(self, target_county: str, target_lot_sqft: float, target_address: str = "") -> CompAnalysis:
        """Run full comp analysis for a target property."""
        land_comps = self._find_land_comps(target_county, target_lot_sqft)
        new_build_comps = self._find_new_build_comps(target_county)
        return self._calculate_metrics(land_comps, new_build_comps)

    def _find_land_comps(self, county: str, target_lot_sqft: float) -> list[LandComp]:
        """Find similar vacant lots sold recently. Filters by county + lot size ±50%."""
        comps: list[LandComp] = []
        target_acres = target_lot_sqft / 43560.0
        min_lot = target_lot_sqft * 0.5
        max_lot = target_lot_sqft * 2.0
        for lead in self._all_leads:
            if lead.get("County", "").strip() != county:
                continue
            lot = float(lead.get("Lot Size Sqft", 0) or 0)
            if lot < min_lot or lot > max_lot:
                continue
            sale_date = lead.get("Last Sale Recording Date", "").strip()
            sale_amount = float(lead.get("Last Sale Amount", 0) or 0)
            if not sale_date or sale_amount <= 0:
                continue
            acres = lot / 43560.0
            comps.append(LandComp(
                address=lead.get("Property Address", "").strip(),
                county=county,
                sale_date=sale_date,
                sale_price=sale_amount,
                lot_size_sqft=lot,
                lot_acres=acres,
                price_per_acre=sale_amount / acres if acres > 0 else 0,
                price_per_sqft=sale_amount / lot if lot > 0 else 0,
                source="tax_assessor",
            ))
        return sorted(comps, key=lambda c: c.sale_date, reverse=True)[:20]

    def _find_new_build_comps(self, county: str) -> list[NewBuildComp]:
        """Find recently built homes in the same county. Uses assessed value + lot data."""
        comps: list[NewBuildComp] = []
        six_months_ago = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
        for lead in self._all_leads:
            if lead.get("County", "").strip() != county:
                continue
            sale_date = lead.get("Last Sale Recording Date", "").strip()
            if sale_date < six_months_ago:
                continue
            sale_amount = float(lead.get("Last Sale Amount", 0) or 0)
            sqft = float(lead.get("Building Sqft", 0) or 0)
            if sale_amount <= 0 or sqft <= 100:
                continue
            assessed = float(lead.get("Total Assessed Value", 0) or 0)
            lot = float(lead.get("Lot Size Sqft", 0) or 0)
            land_cost = assessed * 0.25  # land typically ~25% of assessed value
            year = int(lead.get("Effective Year Built", 0) or 0)
            comps.append(NewBuildComp(
                address=lead.get("Property Address", "").strip(),
                county=county,
                build_year=year,
                land_cost=land_cost,
                construction_cost=max(0, sale_amount - land_cost),
                sale_price=sale_amount,
                sale_date=sale_date,
                sqft=sqft,
                price_per_sqft=sale_amount / sqft if sqft > 0 else 0,
                bedrooms=int(lead.get("Bedrooms", 0) or 0),
                bathrooms=int(float(lead.get("Total Bathrooms", 0) or 0)),
                lot_acres=lot / 43560.0,
                source="tax_assessor",
            ))
        return sorted(comps, key=lambda c: c.sale_date, reverse=True)[:20]

    def _calculate_metrics(self, land_comps: list[LandComp], new_build_comps: list[NewBuildComp]) -> CompAnalysis:
        result = CompAnalysis(land_comps=land_comps, new_build_comps=new_build_comps)
        if land_comps:
            prices_per_acre = [c.price_per_acre for c in land_comps if c.price_per_acre > 0]
            prices_per_sqft = [c.price_per_sqft for c in land_comps if c.price_per_sqft > 0]
            result.avg_land_price_per_acre = sum(prices_per_acre) / len(prices_per_acre) if prices_per_acre else 0
            result.avg_land_price_per_sqft = sum(prices_per_sqft) / len(prices_per_sqft) if prices_per_sqft else 0
            result.comp_count_land = len(land_comps)
        if new_build_comps:
            prices = [c.sale_price for c in new_build_comps if c.sale_price > 0]
            ppsf = [c.price_per_sqft for c in new_build_comps if c.price_per_sqft > 0]
            land_costs = [c.land_cost for c in new_build_comps if c.land_cost > 0]
            result.avg_new_build_sale_price = sum(prices) / len(prices) if prices else 0
            result.avg_new_build_price_per_sqft = sum(ppsf) / len(ppsf) if ppsf else 0
            result.avg_new_build_land_cost = sum(land_costs) / len(land_costs) if land_costs else 0
            result.comp_count_new_build = len(new_build_comps)
        result.estimated_build_value = result.avg_new_build_sale_price
        from plotlot.harness.deal_evaluator import calculate_offer
        result.suggested_offer = calculate_offer(result.estimated_build_value) if result.estimated_build_value > 0 else 0
        return result


def quick_comp_summary(county: str, lot_sqft: float, all_leads: list[dict[str, Any]]) -> dict[str, Any]:
    """Quick comp summary for a single property. Returns key metrics + suggested offer."""
    analyzer = CompAnalyzer(all_leads)
    analysis = analyzer.analyze(county, lot_sqft)
    return {
        **analysis.to_dict(),
        "land_comp_details": [
            {"address": c.address, "sale_price": c.sale_price, "acres": round(c.lot_acres, 1), "per_acre": round(c.price_per_acre, 2)}
            for c in analysis.land_comps[:5]
        ],
        "new_build_details": [
            {"address": c.address, "sale_price": c.sale_price, "sqft": c.sqft, "ppsf": round(c.price_per_sqft, 2), "land_cost": round(c.land_cost, 2)}
            for c in analysis.new_build_comps[:5]
        ],
    }
