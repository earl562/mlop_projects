"""Tests for PDF export (F1) and pro forma (F3) document generation.

Covers:
- Zoning PDF generation from a report dict
- Pro forma compute with rental, sale, zero-revenue, and edge-case scenarios
- API endpoints for PDF download and pro forma JSON/PDF
"""

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.documents.pdf_export import generate_zoning_pdf
from plotlot.documents.proforma import ProFormaInput, compute_pro_forma, generate_pro_forma_pdf


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_REPORT = {
    "address": "171 NE 209th Ter, Miami, FL 33179",
    "formatted_address": "171 NE 209th Ter, Miami Gardens, FL 33179",
    "municipality": "Miami Gardens",
    "county": "Miami-Dade",
    "zoning_district": "RS-4",
    "zoning_description": "Residential Single-Family",
    "max_height": "35 ft",
    "max_density": "4 units/acre",
    "floor_area_ratio": "0.50",
    "lot_coverage": "40%",
    "min_lot_size": "7,500 sqft",
    "parking_requirements": "2 spaces per unit",
    "setbacks": {"front": "25 ft", "side": "10 ft", "rear": "20 ft"},
    "allowed_uses": ["Single-family dwelling", "Accessory dwelling unit"],
    "conditional_uses": ["Home occupation", "Day care"],
    "summary": "This property is zoned RS-4 for single-family residential development.",
    "sources": ["Miami Gardens Zoning Code Sec. 34-100"],
    "confidence": "high",
    "density_analysis": {
        "max_units": 3,
        "governing_constraint": "density",
        "constraints": [
            {
                "name": "density",
                "max_units": 3,
                "raw_value": 4.0,
                "formula": "10,000 sqft * 4 du/acre / 43,560",
                "is_governing": True,
            },
        ],
        "lot_size_sqft": 10000,
    },
    "property_record": {
        "folio": "34-2109-001-0010",
        "owner": "DOE JOHN",
        "lot_size_sqft": 10000.0,
        "lot_dimensions": "100x100",
        "year_built": 1965,
        "living_area_sqft": 1500.0,
        "assessed_value": 250000.0,
        "market_value": 350000.0,
        "last_sale_price": 200000.0,
        "last_sale_date": "2020-01-15",
    },
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# F1 — Zoning PDF Export
# ---------------------------------------------------------------------------


class TestZoningPdfGeneration:
    """Unit tests for generate_zoning_pdf."""

    def test_returns_pdf_bytes(self):
        """PDF bytes should be non-empty and start with the PDF magic number."""
        pdf = generate_zoning_pdf(SAMPLE_REPORT)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:5] == b"%PDF-"

    def test_minimal_report(self):
        """Even a near-empty report should produce valid PDF bytes."""
        pdf = generate_zoning_pdf({"address": "Test", "formatted_address": "Test"})
        assert pdf[:5] == b"%PDF-"

    def test_report_with_no_setbacks(self):
        """A report with empty setbacks should still generate a PDF."""
        report = {**SAMPLE_REPORT, "setbacks": {}}
        pdf = generate_zoning_pdf(report)
        assert pdf[:5] == b"%PDF-"

    def test_report_with_string_uses(self):
        """Handles allowed_uses passed as a JSON string."""
        report = {**SAMPLE_REPORT, "allowed_uses": '["Use A", "Use B"]'}
        pdf = generate_zoning_pdf(report)
        assert pdf[:5] == b"%PDF-"


class TestZoningPdfEndpoint:
    """Integration tests for POST /api/v1/geometry/report/pdf."""

    @pytest.mark.asyncio
    async def test_pdf_download(self, client: AsyncClient):
        """Endpoint returns 200 with PDF content-type and attachment header."""
        resp = await client.post("/api/v1/geometry/report/pdf", json=SAMPLE_REPORT)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "PlotLot_" in resp.headers["content-disposition"]
        assert resp.content[:5] == b"%PDF-"

    @pytest.mark.asyncio
    async def test_pdf_download_minimal(self, client: AsyncClient):
        """Minimal payload still produces a valid PDF response."""
        resp = await client.post(
            "/api/v1/geometry/report/pdf",
            json={
                "address": "123 Test St",
                "formatted_address": "123 Test St, Miami, FL",
                "municipality": "Miami",
                "county": "Miami-Dade",
            },
        )
        assert resp.status_code == 200
        assert resp.content[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# F3 — Pro Forma Computation
# ---------------------------------------------------------------------------


class TestProFormaCompute:
    """Unit tests for compute_pro_forma."""

    def test_rental_scenario(self):
        """Verify NOI, cap rate, and cash-on-cash for a rental scenario."""
        inp = ProFormaInput(
            max_units=4,
            unit_size_sqft=1000,
            land_cost=200_000,
            construction_cost_psf=150,
            soft_cost_pct=15,
            contingency_pct=10,
            ltv_pct=75,
            interest_rate_pct=7,
            loan_term_years=30,
            monthly_rent_per_unit=2000,
            vacancy_pct=5,
            operating_expense_pct=35,
        )
        r = compute_pro_forma(inp)

        # Costs
        assert r.total_buildable_sqft == 4000
        assert r.hard_costs == 600_000  # 4000 * 150
        assert r.soft_costs == 90_000  # 600k * 15%
        assert r.contingency == 60_000  # 600k * 10%
        assert r.total_development_cost == 950_000  # 200k + 600k + 90k + 60k

        # Financing
        assert r.loan_amount == pytest.approx(712_500)  # 950k * 75%
        assert r.equity_required == pytest.approx(237_500)  # 950k * 25%
        assert r.annual_debt_service > 0

        # Revenue
        assert r.gross_annual_income == 96_000  # 4 * 2000 * 12
        assert r.effective_gross_income == pytest.approx(91_200)  # 96k * 95%
        assert r.operating_expenses == pytest.approx(31_920)  # 91.2k * 35%
        assert r.net_operating_income == pytest.approx(59_280)  # 91.2k - 31.92k

        # Returns
        assert r.cap_rate_pct > 0
        expected_cap = (59_280 / 950_000) * 100
        assert r.cap_rate_pct == pytest.approx(expected_cap, rel=1e-3)

    def test_sale_scenario(self):
        """Verify profit and ROI for a sale scenario."""
        inp = ProFormaInput(
            max_units=4,
            unit_size_sqft=1000,
            land_cost=200_000,
            construction_cost_psf=150,
            sale_price_per_unit=350_000,
        )
        r = compute_pro_forma(inp)

        total_cost = r.total_development_cost
        assert r.total_sale_revenue == 1_400_000  # 4 * 350k
        assert r.total_profit == 1_400_000 - total_cost
        assert r.roi_pct == pytest.approx((r.total_profit / total_cost) * 100, rel=1e-3)

    def test_zero_revenue_no_division_error(self):
        """Zero rent and zero sale price should not cause division by zero."""
        inp = ProFormaInput(
            max_units=2,
            unit_size_sqft=800,
            land_cost=100_000,
            construction_cost_psf=120,
            monthly_rent_per_unit=0,
            sale_price_per_unit=0,
        )
        r = compute_pro_forma(inp)

        assert r.gross_annual_income == 0
        assert r.net_operating_income == 0
        assert r.cap_rate_pct == 0
        assert r.cash_on_cash_pct == 0
        assert r.total_sale_revenue == 0
        assert r.roi_pct == 0
        assert r.total_development_cost > 0

    def test_zero_interest_rate(self):
        """Zero interest rate should result in zero debt service without error."""
        inp = ProFormaInput(
            max_units=1,
            unit_size_sqft=1000,
            land_cost=100_000,
            construction_cost_psf=100,
            interest_rate_pct=0,
        )
        r = compute_pro_forma(inp)
        assert r.annual_debt_service == 0

    def test_combined_rental_and_sale(self):
        """Both rental and sale fields populated should compute both."""
        inp = ProFormaInput(
            max_units=2,
            unit_size_sqft=1000,
            land_cost=100_000,
            construction_cost_psf=100,
            monthly_rent_per_unit=1500,
            sale_price_per_unit=300_000,
        )
        r = compute_pro_forma(inp)
        assert r.net_operating_income > 0
        assert r.total_sale_revenue == 600_000
        assert r.roi_pct > 0


class TestProFormaPdf:
    """Unit tests for generate_pro_forma_pdf."""

    def test_returns_pdf_bytes(self):
        """Pro forma PDF should be valid PDF bytes."""
        inp = ProFormaInput(
            address="123 Test St",
            municipality="Miami",
            county="Miami-Dade",
            max_units=4,
            monthly_rent_per_unit=2000,
        )
        pdf = generate_pro_forma_pdf(inp)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:5] == b"%PDF-"

    def test_sale_only_pdf(self):
        """Pro forma PDF with sale-only scenario."""
        inp = ProFormaInput(
            address="456 Sale Ave",
            max_units=2,
            sale_price_per_unit=400_000,
        )
        pdf = generate_pro_forma_pdf(inp)
        assert pdf[:5] == b"%PDF-"

    def test_with_narrative(self):
        """Pro forma PDF with narrative section included."""
        inp = ProFormaInput(
            address="789 Narrative Blvd",
            narrative="This is a prime development opportunity in a growing market.",
        )
        pdf = generate_pro_forma_pdf(inp)
        assert pdf[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# F3 — Pro Forma API Endpoints
# ---------------------------------------------------------------------------


class TestProFormaEndpoints:
    """Integration tests for pro forma API endpoints."""

    @pytest.mark.asyncio
    async def test_proforma_json(self, client: AsyncClient):
        """POST /proforma returns computed values."""
        resp = await client.post(
            "/api/v1/geometry/proforma",
            json={
                "max_units": 4,
                "unit_size_sqft": 1000,
                "land_cost": 200000,
                "construction_cost_psf": 150,
                "monthly_rent_per_unit": 2000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_buildable_sqft"] == 4000
        assert data["hard_costs"] == 600000
        assert data["net_operating_income"] > 0
        assert data["cap_rate_pct"] > 0

    @pytest.mark.asyncio
    async def test_proforma_json_defaults(self, client: AsyncClient):
        """POST /proforma with minimal payload uses defaults."""
        resp = await client.post("/api/v1/geometry/proforma", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_buildable_sqft"] == 1000  # 1 unit * 1000 sqft default
        assert data["total_development_cost"] > 0

    @pytest.mark.asyncio
    async def test_proforma_pdf(self, client: AsyncClient):
        """POST /proforma/pdf returns a PDF download."""
        resp = await client.post(
            "/api/v1/geometry/proforma/pdf",
            json={
                "address": "100 Pro Forma Way",
                "max_units": 6,
                "monthly_rent_per_unit": 1800,
                "sale_price_per_unit": 250000,
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "PlotLot_ProForma_" in resp.headers["content-disposition"]
        assert resp.content[:5] == b"%PDF-"

    @pytest.mark.asyncio
    async def test_proforma_validation_rejects_zero_unit_size(self, client: AsyncClient):
        """unit_size_sqft must be > 0."""
        resp = await client.post(
            "/api/v1/geometry/proforma",
            json={"unit_size_sqft": 0},
        )
        assert resp.status_code == 422
