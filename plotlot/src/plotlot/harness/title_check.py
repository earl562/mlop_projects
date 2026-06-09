"""Title/lien check — basic title search integration for land acquisition.

Per user's due diligence: easements, deed restrictions, liens, title issues.
Integration points for title company API or county recorder data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TitleReport:
    parcel_id: str
    owner_name: str = ""
    status: str = "pending"  # pending, clear, issues_found, review_needed
    easements: list[str] = field(default_factory=list)
    deed_restrictions: list[str] = field(default_factory=list)
    liens: list[dict[str, Any]] = field(default_factory=list)
    mortgages: list[dict[str, Any]] = field(default_factory=list)
    tax_delinquency: bool = False
    last_title_search: str = ""
    title_company: str = ""

    @property
    def is_clear(self) -> bool:
        return not (self.easements or self.deed_restrictions or self.liens or self.tax_delinquency)


class TitleChecker:
    """Basic title search with integration points for title company API."""

    def __init__(self):
        self._reports: dict[str, TitleReport] = {}

    def initiate_check(self, parcel_id: str, owner_name: str) -> TitleReport:
        report = TitleReport(parcel_id=parcel_id, owner_name=owner_name, last_title_search=datetime.now(timezone.utc).isoformat()[:10])
        self._reports[parcel_id] = report
        return report

    def add_easement(self, parcel_id: str, description: str) -> None:
        if parcel_id in self._reports:
            self._reports[parcel_id].easements.append(description)
            self._reports[parcel_id].status = "issues_found"

    def add_lien(self, parcel_id: str, lien_type: str, amount: float, holder: str) -> None:
        if parcel_id in self._reports:
            self._reports[parcel_id].liens.append({"type": lien_type, "amount": amount, "holder": holder})
            self._reports[parcel_id].status = "issues_found"

    def mark_tax_delinquent(self, parcel_id: str) -> None:
        if parcel_id in self._reports:
            self._reports[parcel_id].tax_delinquency = True
            self._reports[parcel_id].status = "issues_found"

    def get_report(self, parcel_id: str) -> TitleReport | None:
        return self._reports.get(parcel_id)

    def due_diligence_checklist(self, parcel_id: str) -> list[str]:
        """Return items that need verification before closing."""
        report = self._reports.get(parcel_id)
        if not report:
            return ["Title search not initiated"]
        items: list[str] = []
        if report.easements:
            items.append(f"Review {len(report.easements)} easement(s)")
        if report.deed_restrictions:
            items.append(f"Review {len(report.deed_restrictions)} deed restriction(s)")
        if report.liens:
            items.append(f"Clear {len(report.liens)} lien(s) at closing")
        if report.tax_delinquency:
            items.append("Resolve tax delinquency before closing")
        return items or ["Title appears clear — proceed to closing"]
