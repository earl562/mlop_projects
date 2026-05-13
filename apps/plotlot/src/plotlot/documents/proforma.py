"""Pro forma financing document generator.

Generates a development pro forma PDF with:
- Project summary (address, zoning, max units)
- Unit mix and sizing
- Cost estimates (land, construction, soft costs)
- Revenue projections (rent or sale)
- Returns analysis (ROI, cash-on-cash, cap rate)

Uses ReportLab for PDF generation. Calculations are deterministic;
LLM narrative sections can be injected via the ``narrative`` parameter.
"""

import io
import logging
from dataclasses import dataclass, field
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

AMBER_700 = colors.HexColor("#b45309")
STONE_800 = colors.HexColor("#292524")
STONE_500 = colors.HexColor("#78716c")
STONE_200 = colors.HexColor("#e7e5e4")


@dataclass
class ProFormaInput:
    """Input parameters for pro forma generation."""

    # Site info
    address: str = ""
    municipality: str = ""
    county: str = ""
    zoning_district: str = ""
    lot_size_sqft: float = 0.0

    # Development parameters
    max_units: int = 1
    unit_size_sqft: float = 1000.0
    stories: int = 1
    parking_spaces: int = 2

    # Cost assumptions (per sqft unless noted)
    land_cost: float = 0.0  # total
    construction_cost_psf: float = 150.0
    soft_cost_pct: float = 15.0  # % of hard costs
    contingency_pct: float = 10.0  # % of hard costs

    # Financing
    ltv_pct: float = 75.0  # loan-to-value
    interest_rate_pct: float = 7.0
    loan_term_years: int = 30

    # Revenue (per unit/month for rental, total for sale)
    monthly_rent_per_unit: float = 0.0
    sale_price_per_unit: float = 0.0
    vacancy_pct: float = 5.0
    operating_expense_pct: float = 35.0  # % of gross income

    # Optional narrative (from LLM)
    narrative: str = ""


@dataclass
class ProFormaResult:
    """Computed pro forma analysis."""

    # Costs
    total_buildable_sqft: float = 0.0
    hard_costs: float = 0.0
    soft_costs: float = 0.0
    contingency: float = 0.0
    total_development_cost: float = 0.0

    # Financing
    loan_amount: float = 0.0
    equity_required: float = 0.0
    annual_debt_service: float = 0.0

    # Revenue
    gross_annual_income: float = 0.0
    effective_gross_income: float = 0.0
    operating_expenses: float = 0.0
    net_operating_income: float = 0.0

    # Returns
    cap_rate_pct: float = 0.0
    cash_on_cash_pct: float = 0.0
    total_profit: float = 0.0
    roi_pct: float = 0.0

    # For sale scenario
    total_sale_revenue: float = 0.0

    notes: list[str] = field(default_factory=list)


def compute_pro_forma(inp: ProFormaInput) -> ProFormaResult:
    """Compute deterministic pro forma from inputs."""
    r = ProFormaResult()

    r.total_buildable_sqft = inp.max_units * inp.unit_size_sqft
    r.hard_costs = r.total_buildable_sqft * inp.construction_cost_psf
    r.soft_costs = r.hard_costs * inp.soft_cost_pct / 100
    r.contingency = r.hard_costs * inp.contingency_pct / 100
    r.total_development_cost = inp.land_cost + r.hard_costs + r.soft_costs + r.contingency

    # Financing
    r.loan_amount = r.total_development_cost * inp.ltv_pct / 100
    r.equity_required = r.total_development_cost - r.loan_amount

    # Annual debt service (standard amortization formula)
    monthly_rate = inp.interest_rate_pct / 100 / 12
    n_payments = inp.loan_term_years * 12
    if monthly_rate > 0 and n_payments > 0:
        monthly_payment = (
            r.loan_amount
            * (monthly_rate * (1 + monthly_rate) ** n_payments)
            / ((1 + monthly_rate) ** n_payments - 1)
        )
        r.annual_debt_service = monthly_payment * 12

    # Revenue — rental scenario
    if inp.monthly_rent_per_unit > 0:
        r.gross_annual_income = inp.max_units * inp.monthly_rent_per_unit * 12
        r.effective_gross_income = r.gross_annual_income * (1 - inp.vacancy_pct / 100)
        r.operating_expenses = r.effective_gross_income * inp.operating_expense_pct / 100
        r.net_operating_income = r.effective_gross_income - r.operating_expenses

        if r.total_development_cost > 0:
            r.cap_rate_pct = (r.net_operating_income / r.total_development_cost) * 100

        annual_cash_flow = r.net_operating_income - r.annual_debt_service
        if r.equity_required > 0:
            r.cash_on_cash_pct = (annual_cash_flow / r.equity_required) * 100

    # Revenue — sale scenario
    if inp.sale_price_per_unit > 0:
        r.total_sale_revenue = inp.max_units * inp.sale_price_per_unit
        r.total_profit = r.total_sale_revenue - r.total_development_cost
        if r.total_development_cost > 0:
            r.roi_pct = (r.total_profit / r.total_development_cost) * 100

    return r


def compute_property_type_summary(
    property_type: str,
    max_units: int,
    lot_size_sqft: float,
    land_cost: float = 0.0,
    avg_unit_size_sqft: float = 1000.0,
) -> dict:
    """Compute property-type-specific financial summary for the report card.

    Returns a dict with property_type, label, metrics, and notes.
    """
    result: dict = {"property_type": property_type, "metrics": {}, "notes": []}

    if property_type == "land":
        result["label"] = "Land / Development Site"
        density_premium = max(1.0, max_units * 0.15 + 1.0)
        est_entitled_value = land_cost * density_premium if land_cost > 0 else 0
        total_buildable = max_units * avg_unit_size_sqft
        est_dev_cost = total_buildable * 175  # rough avg construction cost
        result["metrics"] = {
            "max_units": max_units,
            "total_buildable_sqft": total_buildable,
            "density_premium_factor": round(density_premium, 2),
            "est_entitled_value": round(est_entitled_value),
            "est_development_cost": round(est_dev_cost),
        }
        result["notes"].append("Land valuation uses development potential approach")

    elif property_type == "single_family":
        result["label"] = "Single-Family Residential"
        result["metrics"] = {
            "max_units": max_units,
            "lot_size_sqft": lot_size_sqft,
        }
        result["notes"].append("Single-family valuation uses comparable sales approach")
        result["notes"].append("Provide purchase price and ARV for full analysis")

    elif property_type == "multifamily":
        result["label"] = "Multifamily (2-4 Units)"
        result["metrics"] = {
            "max_units": max_units,
            "lot_size_sqft": lot_size_sqft,
        }
        result["notes"].append("Small multifamily uses hybrid valuation (comps + income)")
        result["notes"].append("Provide rent per unit for NOI and cap rate analysis")

    elif property_type == "commercial_mf":
        result["label"] = "Commercial Multifamily (5+ Units)"
        result["metrics"] = {
            "max_units": max_units,
            "lot_size_sqft": lot_size_sqft,
        }
        result["notes"].append("Commercial MF valued via income approach (NOI / Cap Rate)")
        result["notes"].append("Lenders require DSCR of 1.15-1.25 minimum")

    else:
        result["label"] = "General"
        result["metrics"] = {"max_units": max_units}

    return result


def generate_pro_forma_pdf(inp: ProFormaInput) -> bytes:
    """Generate a pro forma PDF document."""
    result = compute_pro_forma(inp)

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
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=STONE_800,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=STONE_500,
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=AMBER_700,
        spaceBefore=16,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        textColor=STONE_800,
        leading=14,
    )
    note_style = ParagraphStyle(
        "Note",
        parent=styles["Normal"],
        fontSize=9,
        textColor=STONE_500,
        leading=12,
    )

    elements: list = []

    def fmt(val: float) -> str:
        return f"${val:,.0f}"

    def pct(val: float) -> str:
        return f"{val:.1f}%"

    # Header
    elements.append(Paragraph("Development Pro Forma", title_style))
    elements.append(Paragraph(inp.address, subtitle_style))
    elements.append(
        Paragraph(
            f"{inp.municipality}, {inp.county} County | {inp.zoning_district}",
            subtitle_style,
        )
    )
    elements.append(Spacer(1, 8))

    # Narrative (if provided)
    if inp.narrative:
        elements.append(Paragraph("Project Overview", section_style))
        elements.append(Paragraph(inp.narrative, body_style))

    # Project Summary
    elements.append(Paragraph("Project Summary", section_style))
    summary_data = [
        ["Parameter", "Value"],
        ["Total Units", str(inp.max_units)],
        ["Unit Size", f"{inp.unit_size_sqft:,.0f} sqft"],
        ["Total Buildable", f"{result.total_buildable_sqft:,.0f} sqft"],
        ["Stories", str(inp.stories)],
        ["Parking Spaces", str(inp.parking_spaces)],
        ["Lot Size", f"{inp.lot_size_sqft:,.0f} sqft"],
    ]
    elements.append(_make_table(summary_data))

    # Development Costs
    elements.append(Paragraph("Development Costs", section_style))
    cost_data = [
        ["Cost Category", "Amount"],
        ["Land Acquisition", fmt(inp.land_cost)],
        ["Hard Costs (construction)", fmt(result.hard_costs)],
        [f"Soft Costs ({pct(inp.soft_cost_pct)})", fmt(result.soft_costs)],
        [f"Contingency ({pct(inp.contingency_pct)})", fmt(result.contingency)],
        ["Total Development Cost", fmt(result.total_development_cost)],
    ]
    elements.append(_make_table(cost_data, bold_last=True))

    # Financing
    elements.append(Paragraph("Financing Structure", section_style))
    fin_data = [
        ["Parameter", "Value"],
        ["Loan-to-Value", pct(inp.ltv_pct)],
        ["Interest Rate", pct(inp.interest_rate_pct)],
        ["Loan Term", f"{inp.loan_term_years} years"],
        ["Loan Amount", fmt(result.loan_amount)],
        ["Equity Required", fmt(result.equity_required)],
        ["Annual Debt Service", fmt(result.annual_debt_service)],
    ]
    elements.append(_make_table(fin_data))

    # Rental Income (if applicable)
    if inp.monthly_rent_per_unit > 0:
        elements.append(Paragraph("Rental Income Analysis", section_style))
        rental_data = [
            ["Metric", "Annual"],
            ["Gross Rental Income", fmt(result.gross_annual_income)],
            [
                f"Less Vacancy ({pct(inp.vacancy_pct)})",
                fmt(result.gross_annual_income - result.effective_gross_income),
            ],
            ["Effective Gross Income", fmt(result.effective_gross_income)],
            [
                f"Less Operating Expenses ({pct(inp.operating_expense_pct)})",
                fmt(result.operating_expenses),
            ],
            ["Net Operating Income (NOI)", fmt(result.net_operating_income)],
        ]
        elements.append(_make_table(rental_data, bold_last=True))

        elements.append(Paragraph("Returns", section_style))
        returns_data = [
            ["Metric", "Value"],
            ["Cap Rate", pct(result.cap_rate_pct)],
            ["Cash-on-Cash Return", pct(result.cash_on_cash_pct)],
            [
                "Annual Cash Flow",
                fmt(result.net_operating_income - result.annual_debt_service),
            ],
        ]
        elements.append(_make_table(returns_data))

    # Sale Analysis (if applicable)
    if inp.sale_price_per_unit > 0:
        elements.append(Paragraph("Sale Analysis", section_style))
        sale_data = [
            ["Metric", "Value"],
            ["Sale Price per Unit", fmt(inp.sale_price_per_unit)],
            ["Total Sale Revenue", fmt(result.total_sale_revenue)],
            ["Total Development Cost", fmt(result.total_development_cost)],
            ["Profit", fmt(result.total_profit)],
            ["ROI", pct(result.roi_pct)],
        ]
        elements.append(_make_table(sale_data, bold_last=True))

    # Footer
    elements.append(Spacer(1, 20))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elements.append(Paragraph(f"Generated by PlotLot on {now}.", note_style))
    elements.append(
        Paragraph(
            "This pro forma is for preliminary analysis only. Actual costs, revenues, "
            "and returns may vary. Consult with qualified professionals before making "
            "investment decisions.",
            note_style,
        )
    )

    doc.build(elements)
    return buf.getvalue()


def _make_table(data: list[list[str]], bold_last: bool = False) -> Table:
    """Create a styled table."""
    style_cmds: list = [
        ("BACKGROUND", (0, 0), (-1, 0), STONE_200),
        ("TEXTCOLOR", (0, 0), (-1, 0), STONE_800),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, STONE_200),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    if bold_last:
        style_cmds.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
        style_cmds.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")))

    t = Table(data, colWidths=[3 * inch, 3.5 * inch])
    t.setStyle(TableStyle(style_cmds))
    return t
