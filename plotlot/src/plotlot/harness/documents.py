"""Document generation — LOI, purchase contracts, offer letters.

Per user's workflow:
- Send contract after price agreement
- NC purchase contract template provided by user
- LOI (Letter of Intent) for initial offers
- Offer letter with formula explanation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from plotlot.harness.deal_evaluator import OFFER_FORMULA_EXPLANATION
from plotlot.harness.lead_management import VacantLandLead


@dataclass
class OfferLetter:
    buyer: str = "ESP & ME LLC"
    seller: str = ""
    property_address: str = ""
    parcel_id: str = ""
    county: str = ""
    offer_amount: float = 0.0
    lot_acres: float = 0.0
    max_units: int = 1
    earnest_money: float = 250.0
    closing_days: int = 60
    date: str = ""

    def __post_init__(self):
        if not self.date:
            self.date = datetime.now(timezone.utc).strftime("%B %d, %Y")

    def generate(self) -> str:
        return f"""LETTER OF INTENT TO PURCHASE REAL ESTATE

Date: {self.date}

To: {self.seller}
Re: {self.property_address or f'Parcel {self.parcel_id}'}, {self.county} County, NC

Dear Property Owner,

{self.buyer} hereby submits this non-binding Letter of Intent to purchase the above-referenced property.

PROPOSED TERMS:
- Purchase Price: ${self.offer_amount:,.0f}
- Earnest Money Deposit: ${self.earnest_money:,.0f}
- Closing: Within {self.closing_days} days of executed contract
- Property: Vacant land, approximately {self.lot_acres:.1f} acres
- Zoning allows up to {self.max_units} unit(s)

OFFER METHODOLOGY:
{OFFER_FORMULA_EXPLANATION}

The offer is based on comparable land sales in {self.county} County and new construction values in the surrounding area.

NEXT STEPS:
Upon acceptance, we will prepare a formal North Carolina Purchase and Sale Agreement for execution.

This letter is for discussion purposes and does not constitute a binding contract.

Sincerely,
{self.buyer}
"""

    @classmethod
    def from_lead(cls, lead: VacantLandLead, offer_amount: float) -> "OfferLetter":
        return cls(
            seller=lead.owner_name,
            property_address=lead.property_address or lead.apn,
            parcel_id=lead.apn,
            county=lead.county,
            offer_amount=offer_amount,
            lot_acres=lead.lot_acres,
            max_units=lead.max_units,
        )


@dataclass
class PurchaseContract:
    """NC residential purchase contract populated with lead data."""

    buyer: str = "ESP & ME LLC and or assigns"
    seller: str = ""
    property_address: str = ""
    parcel_id: str = ""
    county: str = "Catawba"
    purchase_price: float = 0.0
    earnest_money: float = 250.0
    closing_days: int = 60
    lot_acres: float = 0.0
    date: str = ""

    def __post_init__(self):
        if not self.date:
            self.date = datetime.now(timezone.utc).strftime("%B %d, %Y")

    def generate(self) -> str:
        return f"""REAL ESTATE OFFER TO PURCHASE CONTRACT (RESIDENTIAL)
STATE OF NORTH CAROLINA
COUNTY OF {self.county}

1. PARTIES: {self.seller} (Seller) agrees to sell and convey to {self.buyer} (Purchaser), and Purchaser agrees to buy from Seller the Property described below.

2. PROPERTY: (a) Land: Address: {self.property_address}
   Parcel ID: {self.parcel_id}
   Lot Size: Approximately {self.lot_acres:.1f} acres

3. PURCHASE PRICE: Total Price: ${self.purchase_price:,.0f}
   Cash, certified funds, or loan proceeds due at closing: ${self.purchase_price:,.0f}
   3.a) Earnest Money Deposit: ${self.earnest_money:,.0f}

4. FINANCING: Cash purchase. No financing contingency.

5. TITLE INSURANCE: Seller agrees to furnish a standard form title insurance commitment.

6. PRORATIONS & HAZARD INSURANCE: Taxes prorated as of date of closing.

7. CLOSING COSTS & DATE: Closing within {self.closing_days} days. Buyer pays deed preparation and transfer costs.

8. CONVEYANCE: Seller agrees to convey good merchantable title and General Warranty Deed.

9. CONDITION OF PROPERTY: Property sold "as-is". Purchaser responsible for due diligence.

10. ADDITIONAL PROVISIONS: This offer is subject to satisfactory due diligence including zoning verification, utility availability confirmation, and environmental assessment completed within 30 days of acceptance.

PURCHASER: ___________________________ Date: ___________
SELLER(S): ___________________________ Date: ___________

NOTE: This is a draft for review. Consult legal counsel before signing.
"""

    @classmethod
    def from_lead(cls, lead: VacantLandLead, purchase_price: float) -> "PurchaseContract":
        return cls(
            seller=lead.owner_name,
            property_address=lead.property_address or lead.apn,
            parcel_id=lead.apn,
            county=lead.county,
            purchase_price=purchase_price,
            lot_acres=lead.lot_acres,
        )


class DocumentGenerator:
    """Generate all acquisition documents for a lead."""

    def __init__(self, lead: VacantLandLead, offer_amount: float):
        self.lead = lead
        self.offer = offer_amount

    def loi(self) -> str:
        return OfferLetter.from_lead(self.lead, self.offer).generate()

    def contract(self) -> str:
        return PurchaseContract.from_lead(self.lead, self.offer).generate()

    def due_diligence_checklist(self) -> str:
        from plotlot.harness.deal_evaluator import DUE_DILIGENCE_CHECKLIST
        items = []
        for category, checks in DUE_DILIGENCE_CHECKLIST.items():
            items.append(f"\n{category.upper()}:")
            for c in checks:
                items.append(f"  [ ] {c}")
        return f"DUE DILIGENCE CHECKLIST — {self.lead.property_address or self.lead.apn}\n" + "\n".join(items)

    def offer_summary(self) -> str:
        return f"""OFFER SUMMARY — {self.lead.owner_name}
Property: {self.lead.property_address or self.lead.apn}, {self.lead.county} County, NC
Lot Size: {self.lead.lot_acres:.1f} acres
Offer Amount: ${self.offer:,.0f}
{EARNEST_MONEY}: $250
Closing: 60 days"""
