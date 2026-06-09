"""Land acquisition lead management — pipeline for NC vacant land leads.

Tracks leads through: new → contacted → interested → evaluated → offered → contracted → closed.
Integrates with the sales script questions and follow-up cadence.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class LeadStatus(str, Enum):
    NEW = "new"
    RESEARCHING = "researching"
    CONTACT_ATTEMPT_1 = "contact_1"
    CONTACT_ATTEMPT_2 = "contact_2"
    CONTACT_ATTEMPT_3 = "contact_3"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    EVALUATING = "evaluating"
    OFFER_MADE = "offer_made"
    NEGOTIATING = "negotiating"
    CONTRACT_SENT = "contract_sent"
    CONTRACT_SIGNED = "contract_signed"
    CLOSED = "closed"
    DEAD = "dead"


@dataclass
class VacantLandLead:
    parcel_id: str = ""
    owner_name: str = ""
    owner_first: str = ""
    owner_last: str = ""
    mailing_address: str = ""
    mailing_city: str = ""
    mailing_state: str = ""
    property_address: str = ""
    property_city: str = ""
    property_state: str = ""
    county: str = ""
    apn: str = ""
    lot_size_sqft: float = 0.0
    lot_acres: float = 0.0
    assessed_value: float = 0.0
    last_sale_date: str = ""
    last_sale_amount: float = 0.0
    est_value: float = 0.0
    est_equity: float = 0.0
    owner_occupied: bool = False
    mls_status: str = ""
    mls_amount: float = 0.0
    owner_phones: list[str] = field(default_factory=list)

    # Pipeline tracking
    status: LeadStatus = LeadStatus.NEW
    date_added: str = ""
    last_contact_date: str = ""
    next_follow_up: str = ""
    contact_attempts: int = 0
    notes: list[str] = field(default_factory=list)

    # Evaluation results (filled after EVALUATING stage)
    zoning_compliant: bool | None = None
    utilities_available: bool | None = None
    environmental_flags: list[str] = field(default_factory=list)
    max_units: int = 1
    estimated_offer: float = 0.0
    deal_score: int = 0  # 0-10 based on evaluation

    def age_days(self) -> int:
        if not self.date_added:
            return 0
        try:
            added = datetime.fromisoformat(self.date_added)
            return (datetime.now(timezone.utc) - added).days
        except Exception:
            return 0

    def needs_follow_up(self) -> bool:
        if not self.next_follow_up or self.status in (LeadStatus.CLOSED, LeadStatus.DEAD, LeadStatus.NOT_INTERESTED):
            return False
        try:
            due = datetime.fromisoformat(self.next_follow_up)
            return datetime.now(timezone.utc) >= due
        except Exception:
            return False


class LeadPipeline:
    """Manages the full land acquisition pipeline from lead list to close."""

    def __init__(self):
        self._leads: dict[str, VacantLandLead] = {}

    @classmethod
    def from_csv(cls, csv_content: str) -> "LeadPipeline":
        pipeline = cls()
        reader = csv.DictReader(io.StringIO(csv_content))
        for row in reader:
            lot_size = float(row.get("Lot Size Sqft", 0) or 0)
            if lot_size <= 100:
                continue
            owner_first = row.get("First Name", "").strip()
            owner_last = row.get("Last Name", "").strip()
            if not owner_first and not owner_last:
                continue
            lead = VacantLandLead(
                owner_first=row.get("First Name", "").strip(),
                owner_last=row.get("Last Name", "").strip(),
                owner_name=f"{row.get('First Name', '').strip()} {row.get('Last Name', '').strip()}",
                mailing_address=row.get("Mailing Address", "").strip(),
                mailing_city=row.get("Mailing City", "").strip(),
                mailing_state=row.get("Mailing State", "").strip(),
                property_address=row.get("Property Address", "").strip(),
                property_city=row.get("Property City", "").strip(),
                property_state=row.get("Property State", "").strip(),
                county=row.get("County", "").strip(),
                apn=row.get("APN", "").strip(),
                lot_size_sqft=float(row.get("Lot Size Sqft", 0) or 0),
                lot_acres=float(row.get("Lot Size Sqft", 0) or 0) / 43560.0,
                assessed_value=float(row.get("Total Assessed Value", 0) or 0),
                last_sale_date=row.get("Last Sale Recording Date", "").strip(),
                last_sale_amount=float(row.get("Last Sale Amount", 0) or 0),
                est_value=float(row.get("Est Value", 0) or 0),
                est_equity=float(row.get("Est Equity", 0) or 0),
                owner_occupied=row.get("Owner Occupied", "").strip().lower() == "yes",
                mls_status=row.get("MLS Status", "").strip(),
                mls_amount=float(row.get("MLS Amount", 0) or 0),
                date_added=row.get("Date Added to List", "").strip(),
                owner_phones=[v for k, v in row.items() if "MOBILE" in k and v.strip()],
                status=LeadStatus.NEW,
            )
            lead.parcel_id = lead.apn or f"{lead.county}-{lead.owner_last}-{lead.property_address.replace(' ','')[:10]}"
            pipeline._leads[lead.parcel_id] = lead
        return pipeline

    # ---------------------------------------------------------------- queries
    def by_status(self, status: LeadStatus) -> list[VacantLandLead]:
        return [l for l in self._leads.values() if l.status == status]

    def by_county(self, county: str) -> list[VacantLandLead]:
        return [l for l in self._leads.values() if county.lower() in l.county.lower()]

    def due_for_follow_up(self) -> list[VacantLandLead]:
        return [l for l in self._leads.values() if l.needs_follow_up()]

    def top_deals(self, min_score: int = 5, limit: int = 10) -> list[VacantLandLead]:
        scored = [l for l in self._leads.values() if l.deal_score >= min_score]
        return sorted(scored, key=lambda l: l.deal_score, reverse=True)[:limit]

    def hidden_gems(self) -> list[VacantLandLead]:
        """Lots that could support more units than obvious (single-family zoned but large lot)."""
        return [l for l in self._leads.values() if l.max_units > 1 and l.lot_acres >= 0.5]

    def stats(self) -> dict[str, Any]:
        total = len(self._leads)
        statuses = {}
        for l in self._leads.values():
            statuses[l.status.value] = statuses.get(l.status.value, 0) + 1
        return {"total_leads": total, "by_status": statuses, "due_follow_up": len(self.due_for_follow_up()), "hidden_gems": len(self.hidden_gems()), "counties": {c: len(self.by_county(c)) for c in set(l.county for l in self._leads.values())}}

    # ---------------------------------------------------------------- actions
    def advance(self, parcel_id: str, new_status: LeadStatus, note: str = "") -> VacantLandLead | None:
        lead = self._leads.get(parcel_id)
        if not lead:
            return None
        lead.status = new_status
        if note:
            lead.notes.append(f"[{new_status.value}] {datetime.now(timezone.utc).isoformat()[:10]}: {note}")
        today = datetime.now(timezone.utc).isoformat()[:10]
        lead.last_contact_date = today
        # Auto-schedule follow-up
        if new_status in (LeadStatus.CONTACT_ATTEMPT_1, LeadStatus.CONTACT_ATTEMPT_2):
            lead.next_follow_up = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()[:10]
        elif new_status == LeadStatus.CONTACT_ATTEMPT_3:
            lead.next_follow_up = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()[:10]
        elif new_status == LeadStatus.CONTACTED:
            lead.next_follow_up = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()[:10]
        elif new_status == LeadStatus.OFFER_MADE:
            lead.next_follow_up = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()[:10]
        lead.contact_attempts += 1
        return lead

    def score_deal(self, parcel_id: str, score: int, max_units: int, estimated_offer: float, zoning_compliant: bool, utilities: bool, env_flags: list[str]) -> None:
        lead = self._leads.get(parcel_id)
        if not lead:
            return
        lead.deal_score = score
        lead.max_units = max_units
        lead.estimated_offer = estimated_offer
        lead.zoning_compliant = zoning_compliant
        lead.utilities_available = utilities
        lead.environmental_flags = env_flags

    def get_lead(self, parcel_id: str) -> VacantLandLead | None:
        return self._leads.get(parcel_id)

    @property
    def total_leads(self) -> int:
        return len(self._leads)
