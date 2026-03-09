"""PDF report export — branded zoning analysis document.

Generates a downloadable PDF from a ZoningReportResponse using ReportLab.
Lightweight enough for Render free tier (no external fonts/images required).
"""

import io
import json
import logging
from datetime import datetime, timezone

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

# Brand colors
AMBER_700 = colors.HexColor("#b45309")
STONE_800 = colors.HexColor("#292524")
STONE_500 = colors.HexColor("#78716c")
STONE_200 = colors.HexColor("#e7e5e4")
EMERALD_700 = colors.HexColor("#047857")


def generate_zoning_pdf(report: dict) -> bytes:
    """Generate a PDF from a zoning report dict (ZoningReportResponse.model_dump()).

    Returns PDF as bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=STONE_800,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=STONE_500,
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=AMBER_700,
        spaceBefore=16,
        spaceAfter=8,
        borderWidth=0,
        borderPadding=0,
    )
    body_style = ParagraphStyle(
        "BodyText",
        parent=styles["Normal"],
        fontSize=10,
        textColor=STONE_800,
        leading=14,
    )
    note_style = ParagraphStyle(
        "NoteText",
        parent=styles["Normal"],
        fontSize=9,
        textColor=STONE_500,
        leading=12,
    )

    elements: list = []

    # Title
    elements.append(Paragraph("PlotLot Zoning Analysis", title_style))
    address = report.get("formatted_address") or report.get("address", "")
    municipality = report.get("municipality", "")
    county = report.get("county", "")
    elements.append(Paragraph(f"{address}", subtitle_style))
    elements.append(Paragraph(f"{municipality}, {county} County", subtitle_style))
    elements.append(Spacer(1, 8))

    # Zoning District
    zd = report.get("zoning_district", "")
    zd_desc = report.get("zoning_description", "")
    if zd:
        elements.append(Paragraph("Zoning Classification", section_style))
        elements.append(Paragraph(f"<b>{zd}</b> — {zd_desc}", body_style))

    # Summary
    summary = report.get("summary", "")
    if summary:
        elements.append(Paragraph("Summary", section_style))
        elements.append(Paragraph(summary, body_style))

    # Dimensional Standards table
    dim_rows: list[list[str]] = []
    dim_fields = [
        ("Max Height", "max_height"),
        ("Max Density", "max_density"),
        ("Floor Area Ratio", "floor_area_ratio"),
        ("Lot Coverage", "lot_coverage"),
        ("Min Lot Size", "min_lot_size"),
        ("Parking", "parking_requirements"),
    ]
    for label, key in dim_fields:
        val = report.get(key, "")
        if val and val != "null" and val != "Not specified":
            dim_rows.append([label, val])

    if dim_rows:
        elements.append(Paragraph("Dimensional Standards", section_style))
        dim_rows.insert(0, ["Standard", "Value"])
        t = Table(dim_rows, colWidths=[2.5 * inch, 4 * inch])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), STONE_200),
                    ("TEXTCOLOR", (0, 0), (-1, 0), STONE_800),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(t)

    # Setbacks
    setbacks = report.get("setbacks", {})
    if setbacks:
        sb_rows: list[list[str]] = [["Setback", "Distance"]]
        for label, key in [("Front", "front"), ("Side", "side"), ("Rear", "rear")]:
            val = setbacks.get(key, "")
            if val and val != "null":
                sb_rows.append([label, val])
        if len(sb_rows) > 1:
            elements.append(Paragraph("Setbacks", section_style))
            t = Table(sb_rows, colWidths=[2.5 * inch, 4 * inch])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), STONE_200),
                        ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            elements.append(t)

    # Density Analysis
    density = report.get("density_analysis")
    if density:
        elements.append(Paragraph("Density Analysis", section_style))
        max_units = density.get("max_units", 0)
        governing = density.get("governing_constraint", "")
        elements.append(
            Paragraph(
                f"<b>Maximum Units: {max_units}</b> (governed by: {governing})",
                body_style,
            )
        )

        constraints = density.get("constraints", [])
        if constraints:
            c_rows: list[list[str]] = [["Constraint", "Max Units", "Formula"]]
            for c in constraints:
                marker = " *" if c.get("is_governing") else ""
                c_rows.append(
                    [
                        c.get("name", "") + marker,
                        str(c.get("max_units", "")),
                        c.get("formula", ""),
                    ]
                )
            t = Table(c_rows, colWidths=[2 * inch, 1.2 * inch, 3.3 * inch])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), STONE_200),
                        ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            elements.append(t)

    # Permitted Uses
    for label, key in [
        ("Allowed Uses", "allowed_uses"),
        ("Conditional Uses", "conditional_uses"),
    ]:
        uses = report.get(key, [])
        if uses:
            elements.append(Paragraph(label, section_style))
            if isinstance(uses, str):
                try:
                    uses = json.loads(uses)
                except (json.JSONDecodeError, TypeError):
                    uses = [uses]
            bullet_text = "<br/>".join(f"&bull; {u}" for u in uses)
            elements.append(Paragraph(bullet_text, body_style))

    # Property Record
    prop = report.get("property_record")
    if prop:
        elements.append(Paragraph("Property Record", section_style))
        prop_rows: list[list[str]] = [["Field", "Value"]]
        prop_fields = [
            ("Folio", "folio"),
            ("Owner", "owner"),
            ("Lot Size", "lot_size_sqft"),
            ("Lot Dimensions", "lot_dimensions"),
            ("Year Built", "year_built"),
            ("Living Area", "living_area_sqft"),
            ("Assessed Value", "assessed_value"),
            ("Market Value", "market_value"),
            ("Last Sale Price", "last_sale_price"),
            ("Last Sale Date", "last_sale_date"),
        ]
        for label, key in prop_fields:
            val = prop.get(key, "")
            if val and val != 0 and val != 0.0:
                if isinstance(val, float) and val > 100:
                    val = f"{val:,.0f}"
                prop_rows.append([label, str(val)])
        if len(prop_rows) > 1:
            t = Table(prop_rows, colWidths=[2.5 * inch, 4 * inch])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), STONE_200),
                        ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            elements.append(t)

    # Sources
    sources = report.get("sources", [])
    if sources:
        elements.append(Paragraph("Sources", section_style))
        for src in sources:
            elements.append(Paragraph(f"&bull; {src}", note_style))

    # Footer
    elements.append(Spacer(1, 20))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elements.append(
        Paragraph(
            f"Generated by PlotLot on {now}. Confidence: {report.get('confidence', 'N/A')}.",
            note_style,
        )
    )
    elements.append(
        Paragraph(
            "This report is for informational purposes only. "
            "Verify all zoning requirements with the local municipality.",
            note_style,
        )
    )

    doc.build(elements)
    return buf.getvalue()
