"""Deal Paper — one-page investment memo (the demo/lead artifact).

Combines everything PlotLot already computes — property, zoning, max buildable
units, comparable-sales price range, the residual pro forma, and site risk —
into a single branded one-pager a developer can forward to a capital partner.

Distinct from:
  - ``pdf_export.generate_zoning_pdf`` — the long informational zoning report.
  - the Clause Builder LOI/PSA — the legal deal paper.

Input is a ``ZoningReportResponse.model_dump()`` dict, so it reflects the live
pipeline output (including the ADV/price-range fields added to the comps step).
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# Warm Cartography brand palette
AMBER_700 = colors.HexColor("#b45309")
AMBER_100 = colors.HexColor("#fef3c7")
STONE_900 = colors.HexColor("#1c1917")
STONE_800 = colors.HexColor("#292524")
STONE_500 = colors.HexColor("#78716c")
STONE_200 = colors.HexColor("#e7e5e4")
STONE_50 = colors.HexColor("#fafaf9")
EMERALD_700 = colors.HexColor("#047857")
RED_700 = colors.HexColor("#b91c1c")


def _fmt_money(val: Any) -> str:
    """Format a number as whole dollars, or an em dash when absent."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return "—"
    if f == 0:
        return "—"
    return f"${f:,.0f}"


def _fmt_range(low: Any, high: Any) -> str:
    """Format a low–high band; collapses to a single value when equal/absent."""
    lo = _fmt_money(low)
    hi = _fmt_money(high)
    if lo == "—" and hi == "—":
        return "—"
    if lo == hi or hi == "—":
        return lo
    if lo == "—":
        return hi
    return f"{lo} – {hi}"


def generate_deal_paper_pdf(report: dict) -> bytes:
    """Generate a one-page investment memo PDF from a zoning report dict."""
    density = report.get("density_analysis") or {}
    comps = report.get("comp_analysis") or {}
    pf = report.get("pro_forma") or {}
    risk = report.get("site_risk") or {}
    prop = report.get("property_record") or {}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        title="PlotLot Investment Memo",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DealTitle", parent=styles["Heading1"], fontSize=18, textColor=STONE_900, spaceAfter=2
    )
    subtitle_style = ParagraphStyle(
        "DealSubtitle", parent=styles["Normal"], fontSize=10.5, textColor=STONE_500, spaceAfter=2
    )
    section_style = ParagraphStyle(
        "DealSection",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=AMBER_700,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "DealBody", parent=styles["Normal"], fontSize=9.5, textColor=STONE_800, leading=13
    )
    note_style = ParagraphStyle(
        "DealNote", parent=styles["Normal"], fontSize=8, textColor=STONE_500, leading=11
    )
    hero_label_style = ParagraphStyle(
        "HeroLabel", parent=styles["Normal"], fontSize=8, textColor=STONE_500, alignment=1
    )
    hero_value_style = ParagraphStyle(
        "HeroValue", parent=styles["Normal"], fontSize=15, textColor=STONE_900, alignment=1
    )

    elements: list = []

    # --- Header ---
    address = report.get("formatted_address") or report.get("address", "")
    municipality = report.get("municipality", "")
    county = report.get("county", "")
    elements.append(Paragraph("Investment Memo", title_style))
    elements.append(Paragraph(f"<b>{address}</b>", subtitle_style))
    locale = ", ".join(p for p in [municipality, f"{county} County" if county else ""] if p)
    zoning_district = report.get("zoning_district", "")
    locale_line = " · ".join(p for p in [locale, zoning_district] if p)
    if locale_line:
        elements.append(Paragraph(locale_line, subtitle_style))
    elements.append(Spacer(1, 10))

    # --- Hero metrics ---
    max_offer = pf.get("max_land_price", 0)
    max_units = density.get("max_units", 0)
    land_value_band = _fmt_range(
        comps.get("estimated_land_value_low"), comps.get("estimated_land_value_high")
    )
    if land_value_band == "—":
        land_value_band = _fmt_money(comps.get("estimated_land_value"))
    adv_per_unit = pf.get("adv_per_unit") or comps.get("adv_per_unit") or 0

    def _hero_cell(label: str, value: str) -> list:
        return [Paragraph(label, hero_label_style), Paragraph(f"<b>{value}</b>", hero_value_style)]

    hero_data = [
        [
            _hero_cell("MAX OFFER (RESIDUAL)", _fmt_money(max_offer)),
            _hero_cell("MAX UNITS", str(max_units) if max_units else "—"),
            _hero_cell("EST. LAND VALUE", land_value_band),
            _hero_cell("ADV / UNIT", _fmt_money(adv_per_unit)),
        ]
    ]
    hero = Table(hero_data, colWidths=[1.72 * inch] * 4, rowHeights=[0.72 * inch])
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), AMBER_100),
                ("BACKGROUND", (1, 0), (-1, 0), STONE_50),
                ("BOX", (0, 0), (-1, -1), 0.75, STONE_200),
                ("INNERGRID", (0, 0), (-1, -1), 0.75, STONE_200),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(hero)
    elements.append(Spacer(1, 4))

    # --- Deal at a glance ---
    elements.append(Paragraph("Deal at a Glance", section_style))
    governing = density.get("governing_constraint", "")
    lot_sqft = prop.get("lot_size_sqft") or report.get("lot_size_sqft") or 0
    glance_rows = [
        [
            "Zoning District",
            zoning_district or "—",
            "Max Units",
            str(max_units) if max_units else "—",
        ],
        [
            "Lot Size",
            f"{float(lot_sqft):,.0f} sqft" if lot_sqft else "—",
            "Governing Constraint",
            governing or "—",
        ],
        [
            "Market",
            pf.get("market") or "—",
            "Owner",
            prop.get("owner") or "—",
        ],
    ]
    elements.append(_kv_table(glance_rows))

    # --- Valuation & pricing (the price range is front and center) ---
    elements.append(Paragraph("Valuation & Pricing (within 3 mi)", section_style))
    comp_count = len(comps.get("comparables") or [])
    unit_comp_count = len(comps.get("unit_comparables") or [])
    confidence_pct = f"{float(comps.get('confidence', 0)) * 100:.0f}%"
    val_rows = [
        ["Metric", "Low (P25)", "Median", "High (P75)"],
        [
            "Land $/acre",
            _fmt_money(comps.get("price_per_acre_low")),
            _fmt_money(comps.get("median_price_per_acre")),
            _fmt_money(comps.get("price_per_acre_high")),
        ],
        [
            "Est. land value",
            _fmt_money(comps.get("estimated_land_value_low")),
            _fmt_money(comps.get("estimated_land_value")),
            _fmt_money(comps.get("estimated_land_value_high")),
        ],
        [
            "ADV / unit (exit)",
            _fmt_money(comps.get("adv_per_unit_low")),
            _fmt_money(comps.get("adv_per_unit")),
            _fmt_money(comps.get("adv_per_unit_high")),
        ],
    ]
    elements.append(_range_table(val_rows))
    adv_src = comps.get("adv_source") or pf.get("adv_source") or ""
    src_label = {
        "comps": f"{unit_comp_count} sold-unit comp(s)",
        "regional_default": "regional market estimate (no sold-unit comps found)",
        "comps_land_value": "land value only (no ADV available)",
        "override": "user-supplied",
    }.get(adv_src, "n/a")
    elements.append(
        Paragraph(
            f"Based on <b>{comp_count}</b> land comp(s), confidence <b>{confidence_pct}</b>. "
            f"ADV source: {src_label}.",
            note_style,
        )
    )

    # --- Residual pro forma ---
    if pf.get("max_units"):
        elements.append(Paragraph("Residual Pro Forma", section_style))
        pf_rows = [
            ["Gross Development Value", _fmt_money(pf.get("gross_development_value"))],
            ["Hard Costs", _fmt_money(pf.get("hard_costs"))],
            ["Soft Costs", _fmt_money(pf.get("soft_costs"))],
            ["Builder Margin", _fmt_money(pf.get("builder_margin"))],
            ["Cost per Door", _fmt_money(pf.get("cost_per_door"))],
            ["Maximum Land Offer", _fmt_money(pf.get("max_land_price"))],
        ]
        elements.append(_kv2_table(pf_rows, highlight_last=True))
        assumptions = (
            f"Assumptions: ${float(pf.get('construction_cost_psf', 0)):,.0f}/sf hard cost · "
            f"{float(pf.get('soft_cost_pct', 0)):.0f}% soft · "
            f"{float(pf.get('builder_margin_pct', 0)):.0f}% margin · "
            f"{float(pf.get('avg_unit_size_sqft', 0)):,.0f} sf/unit"
        )
        elements.append(Paragraph(assumptions, note_style))

    # --- Site risk ---
    flood = risk.get("flood_zone") or {}
    risk_flags = risk.get("risk_flags") or []
    if flood or risk_flags or risk.get("has_wetlands"):
        elements.append(Paragraph("Site Risk", section_style))
        bits = []
        if flood:
            bits.append(
                f"FEMA flood zone <b>{flood.get('zone', 'N/A')}</b> ({flood.get('risk_level', 'unknown')} risk)"
            )
        if risk.get("has_wetlands"):
            bits.append("NWI wetlands present")
        overall = risk.get("overall_risk")
        if overall and overall != "unknown":
            bits.append(f"overall risk <b>{overall}</b>")
        elements.append(
            Paragraph(" · ".join(bits) if bits else "No significant flags.", body_style)
        )
        for flag in risk_flags[:4]:
            elements.append(Paragraph(f"&bull; {flag}", note_style))

    # --- Recommendation ---
    elements.append(Paragraph("Assessment", section_style))
    summary = report.get("summary", "")
    if summary:
        elements.append(Paragraph(summary, body_style))
    verdict, verdict_color = _verdict(max_offer, comps.get("confidence", 0))
    verdict_style = ParagraphStyle(
        "Verdict", parent=body_style, textColor=verdict_color, fontSize=10, spaceBefore=4
    )
    elements.append(Paragraph(f"<b>Suggested next step:</b> {verdict}", verdict_style))

    # --- Footer ---
    elements.append(Spacer(1, 12))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elements.append(
        Paragraph(
            f"Generated by PlotLot on {now}. Confidence: {report.get('confidence', 'N/A')}. "
            "Preliminary analysis only — verify zoning, costs, and comps before transacting.",
            note_style,
        )
    )

    doc.build(elements)
    return buf.getvalue()


def _verdict(max_offer: Any, confidence: Any) -> tuple[str, colors.Color]:
    """Derive a neutral, evidence-based next-step suggestion."""
    try:
        offer = float(max_offer)
    except (TypeError, ValueError):
        offer = 0.0
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 0.0
    if offer <= 0:
        return (
            "Negative/zero residual at current assumptions — revisit unit count, costs, or ADV.",
            RED_700,
        )
    if conf >= 0.75:
        return (
            "Comps support the valuation — proceed to diligence and validate the offer ceiling.",
            EMERALD_700,
        )
    return (
        "Residual is positive but comp confidence is thin — confirm ADV with local sold-unit data.",
        AMBER_700,
    )


def _kv_table(rows: list[list[str]]) -> Table:
    """Four-column key/value grid (label, value, label, value)."""
    t = Table(rows, colWidths=[1.5 * inch, 1.95 * inch, 1.6 * inch, 1.95 * inch])
    t.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), STONE_500),
                ("TEXTCOLOR", (2, 0), (2, -1), STONE_500),
                ("TEXTCOLOR", (1, 0), (1, -1), STONE_800),
                ("TEXTCOLOR", (3, 0), (3, -1), STONE_800),
                ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def _kv2_table(rows: list[list[str]], highlight_last: bool = False) -> Table:
    """Two-column label/value table."""
    style_cmds = [
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), STONE_800),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    if highlight_last:
        style_cmds.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
        style_cmds.append(("BACKGROUND", (0, -1), (-1, -1), AMBER_100))
        style_cmds.append(("TEXTCOLOR", (0, -1), (-1, -1), STONE_900))
    t = Table(rows, colWidths=[3.6 * inch, 3.4 * inch])
    t.setStyle(TableStyle(style_cmds))
    return t


def _range_table(rows: list[list[str]]) -> Table:
    """Header + low/median/high range table."""
    t = Table(rows, colWidths=[2.2 * inch, 1.6 * inch, 1.6 * inch, 1.6 * inch])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), STONE_200),
                ("TEXTCOLOR", (0, 0), (-1, 0), STONE_800),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t
