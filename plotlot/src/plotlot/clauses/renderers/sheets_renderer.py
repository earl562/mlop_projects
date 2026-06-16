"""Google Sheets renderer — wraps google_workspace.py for pro forma output.

Creates a multi-tab Google Sheet from DealContext data using the existing
Google Workspace integration (OAuth2 refresh token flow).

This is an async renderer — unlike docx/xlsx which return bytes,
this returns a SpreadsheetResult with the shareable Google Sheets URL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from plotlot.clauses.schema import AssemblyConfig, DealContext, RenderedClause
from plotlot.retrieval.google_workspace import SpreadsheetResult, create_spreadsheet

logger = logging.getLogger(__name__)


def _fmt_currency(value: float) -> str:
    return f"${value:,.0f}"


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


@dataclass
class SheetsProFormaResult:
    """Result from Google Sheets pro forma generation."""

    spreadsheet_id: str
    spreadsheet_url: str
    title: str


def _build_pro_forma_rows(context: DealContext) -> tuple[list[str], list[list[str]]]:
    """Build headers and rows for the pro forma spreadsheet.

    Returns a single-sheet representation with sections separated by
    blank rows, suitable for create_spreadsheet().
    """
    headers = ["Category", "Metric", "Value"]

    land = context.purchase_price or context.estimated_land_value or 0
    hard = context.hard_costs
    soft = context.soft_costs
    contingency = hard * 0.10 if hard else 0
    total_cost = land + hard + soft + contingency
    gdv = context.gross_development_value
    profit = gdv - total_cost
    roi = (profit / total_cost * 100) if total_cost > 0 else 0

    rows: list[list[str]] = [
        # Property summary
        ["Property", "Address", context.property_address or "—"],
        ["Property", "Municipality", context.municipality or "—"],
        ["Property", "County", context.county or "—"],
        ["Property", "APN", context.apn or "—"],
        [
            "Property",
            "Lot Size (sqft)",
            f"{context.lot_size_sqft:,.0f}" if context.lot_size_sqft else "—",
        ],
        ["Property", "Zoning District", context.zoning_district or "—"],
        ["Property", "Max Units", str(context.max_units) if context.max_units else "—"],
        ["Property", "Governing Constraint", context.governing_constraint or "—"],
        ["", "", ""],
        # Development costs
        ["Costs", "Land Acquisition", _fmt_currency(land)],
        ["Costs", "Hard Costs", _fmt_currency(hard)],
        ["Costs", "Soft Costs", _fmt_currency(soft)],
        ["Costs", "Contingency (10%)", _fmt_currency(contingency)],
        ["Costs", "Total Development Cost", _fmt_currency(total_cost)],
        ["", "", ""],
        # Revenue
        ["Revenue", "Gross Development Value", _fmt_currency(gdv)],
        ["Revenue", "Builder Margin", _fmt_currency(context.builder_margin)],
        ["Revenue", "Max Land Price", _fmt_currency(context.max_land_price)],
        ["Revenue", "ADV per Unit", _fmt_currency(context.adv_per_unit)],
        ["", "", ""],
        # Financing
        ["Financing", "Deal Type", context.deal_type.value.replace("_", " ").title()],
        ["Financing", "Purchase Price", _fmt_currency(context.purchase_price)],
        ["Financing", "Earnest Money", _fmt_currency(context.earnest_money)],
    ]

    if context.existing_mortgage_balance_1:
        rows.extend(
            [
                [
                    "Financing",
                    "Existing Mortgage",
                    _fmt_currency(context.existing_mortgage_balance_1),
                ],
                ["Financing", "Existing Payment", _fmt_currency(context.existing_mortgage_payment)],
            ]
        )

    if context.seller_carryback_amount:
        rows.extend(
            [
                ["Financing", "Seller Carryback", _fmt_currency(context.seller_carryback_amount)],
                ["Financing", "Carryback Rate", _fmt_pct(context.seller_carryback_rate)],
            ]
        )

    rows.extend(
        [
            ["", "", ""],
            # Returns
            ["Returns", "Total Profit", _fmt_currency(profit)],
            ["Returns", "ROI", _fmt_pct(roi)],
        ]
    )

    if context.max_units and context.max_units > 0:
        rows.append(["Returns", "Profit per Unit", _fmt_currency(profit / context.max_units)])

    # Comps
    if context.median_price_per_acre:
        rows.extend(
            [
                ["", "", ""],
                ["Comps", "Median $/Acre", _fmt_currency(context.median_price_per_acre)],
                ["Comps", "Est. Land Value", _fmt_currency(context.estimated_land_value)],
                ["Comps", "Comp Count", str(context.comp_count)],
            ]
        )

    return headers, rows


async def render_google_sheets(
    clauses: list[RenderedClause],
    config: AssemblyConfig,
    context: DealContext,
) -> SheetsProFormaResult:
    """Create a Google Sheets pro forma from DealContext data.

    Wraps the existing google_workspace.create_spreadsheet() with
    pro forma-specific data formatting.

    Args:
        clauses: Rendered clauses (metadata only for sheets).
        config: Assembly configuration.
        context: DealContext with financial and property data.

    Returns:
        SheetsProFormaResult with the shareable Google Sheets URL.
    """
    address = context.property_address or context.formatted_address or "Property"
    short_addr = address.split(",")[0][:40]
    title = f"PlotLot Pro Forma — {short_addr}"

    headers, rows = _build_pro_forma_rows(context)

    result: SpreadsheetResult = await create_spreadsheet(
        title=title,
        headers=headers,
        rows=rows,
    )

    logger.info("Created Google Sheets pro forma: %s", result.spreadsheet_url)
    return SheetsProFormaResult(
        spreadsheet_id=result.spreadsheet_id,
        spreadsheet_url=result.spreadsheet_url,
        title=result.title,
    )
