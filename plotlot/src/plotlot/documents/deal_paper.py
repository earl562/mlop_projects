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
    verification = report.get("extraction_verification") or {}
    provisional = bool(verification.get("offer_is_provisional"))

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

    offer_label = "MAX OFFER (PROVISIONAL)" if provisional else "MAX OFFER (RESIDUAL)"
    hero_data = [
        [
            _hero_cell(offer_label, _fmt_money(max_offer)),
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

    # --- Plausibility warnings (verify before relying) ---
    warnings = report.get("warnings") or []
    if warnings:
        warn_style = ParagraphStyle(
            "Warn", parent=note_style, fontSize=8.5, textColor=STONE_800, leading=12
        )
        warn_text = "<br/>".join(f"&bull; {w}" for w in warnings)
        warn_para = Paragraph(
            '<b><font color="#b91c1c">Verify before relying on these numbers</font></b>'
            f"<br/>{warn_text}",
            warn_style,
        )
        box = Table([[warn_para]], colWidths=[6.9 * inch])
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), AMBER_100),
                    ("BOX", (0, 0), (-1, -1), 1, RED_700),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(box)
        elements.append(Spacer(1, 6))

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

    # --- Source verification (every value-driver corroborated or flagged) ---
    ver_fields = verification.get("fields") or []
    if ver_fields:
        elements.append(Paragraph("Source Verification", section_style))
        elements.append(_verification_table(ver_fields))
        overall = verification.get("overall", "unverified")
        elements.append(
            Paragraph(
                f"Overall: <b>{overall}</b>. Values are checked against the ordinance text and "
                "the zoning code; unverified drivers make the offer provisional.",
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
            ["Impact / Development Fees", _fmt_money(pf.get("impact_fees"))],
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

    # --- Entitlement & fees (what it takes to build) ---
    ent = report.get("entitlement") or {}
    if ent.get("path"):
        elements.append(Paragraph("Entitlement & Fees", section_style))
        path = str(ent.get("path") or "unknown")
        path_label = {
            "by_right": "By-right",
            "conditional_use": "Conditional-use permit",
            "rezoning": "Rezoning required",
            "unknown": "Path unverified",
        }.get(path, path)
        complexity = str(ent.get("complexity") or "—").title()
        ent_rows: list[list[str]] = [
            ["Approval path", path_label, "Complexity", complexity],
            [
                "Est. timeline",
                f"{float(ent.get('est_timeline_months', 0)):.0f} mo",
                "Impact fees",
                f"{_fmt_money(ent.get('impact_fees_total'))} "
                f"({_fmt_money(ent.get('impact_fee_per_unit'))}/unit)",
            ],
        ]
        elements.append(_kv_table(ent_rows))
        steps = ent.get("steps") or []
        if steps:
            step_text = " · ".join(
                f"{s.get('name')} ({s.get('status')}, {float(s.get('timeline_months', 0)):.0f}mo)"
                for s in steps
            )
            elements.append(Paragraph(step_text, note_style))
        if ent.get("utilities_note"):
            elements.append(Paragraph(ent["utilities_note"], note_style))

    # --- Development upside (CA state programs) — additive, not the firm count ---
    uplift = report.get("density_uplift") or {}
    programs = uplift.get("programs") or []
    if programs:
        base_u = uplift.get("base_units", 0)
        max_u = uplift.get("max_potential_units", base_u)
        elements.append(Paragraph("Development Upside — CA State Programs", section_style))
        up_rows = [["Program", "Potential Units", "Requires"]]
        for p in programs:
            eligible = p.get("eligibility", "eligible") == "eligible"
            potential = (
                f"{base_u} → {p.get('potential_units', base_u)}"
                if eligible
                else "restricted — verify"
            )
            tag = (
                " — local (verified)"
                if p.get("source") == "local"
                else f" ({p.get('statute', '')})"
            )
            up_rows.append(
                [
                    f"{p.get('name', '')}{tag}",
                    potential,
                    p.get("requirements", ""),
                ]
            )
        elements.append(_uplift_table(up_rows))
        elements.append(
            Paragraph(
                f"Base zoning is the firm count ({base_u} units); state programs could reach "
                f"<b>up to {max_u} units</b> as upside. Additive (not stacked) — confirm "
                "eligibility with a land-use attorney. Does not change the offer above.",
                note_style,
            )
        )

    # --- Sensitivity (max offer vs. ADV × construction cost) ---
    sens = _resolve_sensitivity(report.get("sensitivity"), pf)
    if sens and sens.get("grid"):
        elements.append(Paragraph("Sensitivity — Max Offer", section_style))
        elements.append(_sensitivity_grid(sens))
        elements.append(
            Paragraph(
                "Max land offer as ADV per unit (columns) and construction $/sf (rows) "
                "swing ±20%. Green = deal pencils; red = upside-down.",
                note_style,
            )
        )

    # --- Site risk ---
    flood = risk.get("flood_zone") or {}
    risk_flags = risk.get("risk_flags") or []
    coastal = report.get("coastal_overlay") or {}
    coastal_relevant = coastal.get("status") in ("in", "unverified")
    if flood or risk_flags or risk.get("has_wetlands") or coastal_relevant:
        elements.append(Paragraph("Site Risk", section_style))
        bits = []
        if flood:
            bits.append(
                f"FEMA flood zone <b>{flood.get('zone', 'N/A')}</b> ({flood.get('risk_level', 'unknown')} risk)"
            )
        if risk.get("has_wetlands"):
            bits.append("NWI wetlands present")
        if coastal.get("status") == "in" and coastal.get("height_limit_ft"):
            bits.append(f"Coastal height limit <b>{coastal['height_limit_ft']:g} ft</b> (Prop D)")
        overall = risk.get("overall_risk")
        if overall and overall != "unknown":
            bits.append(f"overall risk <b>{overall}</b>")
        elements.append(
            Paragraph(" · ".join(bits) if bits else "No significant flags.", body_style)
        )
        for flag in risk_flags[:4]:
            elements.append(Paragraph(f"&bull; {flag}", note_style))
        if coastal_relevant and coastal.get("note"):
            elements.append(Paragraph(f"&bull; {coastal['note']}", note_style))

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


# Sensitivity-grid shading
EMERALD_50 = colors.HexColor("#ecfdf5")
RED_50 = colors.HexColor("#fef2f2")

_VER_BADGE = {"verified": "VERIFIED", "conflict": "CONFLICT", "unverified": "UNVERIFIED"}
_VER_COLOR = {"verified": EMERALD_700, "conflict": RED_700, "unverified": AMBER_700}


def _fmt_val(v: Any) -> str:
    """Format an extracted numeric value for the verification table."""
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:g}"


def _uplift_table(rows: list[list[str]]) -> Table:
    """Render the CA state-program upside table (program | potential | requires)."""
    body = [
        [Paragraph(c, ParagraphStyle("u", fontSize=8, leading=10)) for c in row] for row in rows
    ]
    t = Table(body, colWidths=[2.3 * inch, 1.3 * inch, 3.3 * inch])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), STONE_200),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def _verification_table(fields: list[dict]) -> Table:
    """Render per-value verification: extracted vs. source, with a status badge."""
    rows = [["Value", "Extracted", "Source", "Status"]]
    status_by_row: list[str] = []
    for fv in fields:
        status = fv.get("status", "unverified")
        status_by_row.append(status)
        rows.append(
            [
                fv.get("label", fv.get("field", "")),
                _fmt_val(fv.get("llm_value")),
                _fmt_val(fv.get("source_value")),
                _VER_BADGE.get(status, status.upper()),
            ]
        )

    style_cmds: list = [
        ("BACKGROUND", (0, 0), (-1, 0), STONE_200),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i, status in enumerate(status_by_row):
        style_cmds.append(("TEXTCOLOR", (3, i + 1), (3, i + 1), _VER_COLOR.get(status, STONE_800)))
        style_cmds.append(("FONTNAME", (3, i + 1), (3, i + 1), "Helvetica-Bold"))

    t = Table(rows, colWidths=[2.7 * inch, 1.4 * inch, 1.4 * inch, 1.4 * inch])
    t.setStyle(TableStyle(style_cmds))
    return t


def _fmt_compact(val: Any) -> str:
    """Compact money for dense grids: $1.2M / $760K / -$45K / —."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return "—"
    if f == 0:
        return "—"
    neg = f < 0
    f = abs(f)
    if f >= 1_000_000:
        s = f"${f / 1_000_000:.1f}M"
    elif f >= 1_000:
        s = f"${f / 1_000:.0f}K"
    else:
        s = f"${f:,.0f}"
    return f"-{s}" if neg else s


def _resolve_sensitivity(sens: dict | None, pf: dict) -> dict | None:
    """Use the report's sensitivity table, or compute one from pro-forma values."""
    if sens and sens.get("grid"):
        return sens
    units = pf.get("max_units") or 0
    adv = pf.get("adv_per_unit") or 0
    if not units or adv <= 0:
        return None
    from dataclasses import asdict

    from plotlot.pipeline.sensitivity import build_sensitivity_table

    table = build_sensitivity_table(
        max_units=int(units),
        adv_per_unit=float(adv),
        construction_cost_psf=float(pf.get("construction_cost_psf") or 0) or None,
        avg_unit_size_sqft=float(pf.get("avg_unit_size_sqft") or 0) or None,
        soft_cost_pct=float(pf.get("soft_cost_pct") or 0) or None,
        builder_margin_pct=float(pf.get("builder_margin_pct") or 0) or None,
    )
    return asdict(table)


def _sensitivity_grid(sens: dict) -> Table:
    """Render the 2-way sensitivity grid with green/red shading + base highlight."""
    col_values = sens.get("col_values", [])
    row_values = sens.get("row_values", [])
    grid = sens.get("grid", [])
    base_r = sens.get("base_row_index", 0)
    base_c = sens.get("base_col_index", 0)

    header = ["$/sf ↓  ADV →"] + [_fmt_compact(v) for v in col_values]
    data = [header]
    for r, cost in enumerate(row_values):
        row = [f"${float(cost):,.0f}"] + [_fmt_compact(grid[r][c]) for c in range(len(col_values))]
        data.append(row)

    style_cmds: list = [
        ("BACKGROUND", (0, 0), (-1, 0), STONE_200),
        ("BACKGROUND", (0, 0), (0, -1), STONE_200),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    # Per-cell green/red shading by feasibility.
    for r in range(len(row_values)):
        for c in range(len(col_values)):
            color = EMERALD_50 if grid[r][c] > 0 else RED_50
            style_cmds.append(("BACKGROUND", (c + 1, r + 1), (c + 1, r + 1), color))

    # Highlight the base case.
    style_cmds.append(("BOX", (base_c + 1, base_r + 1), (base_c + 1, base_r + 1), 1.5, AMBER_700))
    style_cmds.append(
        ("FONTNAME", (base_c + 1, base_r + 1), (base_c + 1, base_r + 1), "Helvetica-Bold")
    )

    n_cols = len(col_values) + 1
    first = 1.25 * inch
    rest = (6.8 * inch - first) / max(n_cols - 1, 1)
    t = Table(data, colWidths=[first] + [rest] * (n_cols - 1))
    t.setStyle(TableStyle(style_cmds))
    return t
