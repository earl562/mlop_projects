"""Tests for the document generation API endpoints."""

from __future__ import annotations


import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app


@pytest.fixture
def base_url() -> str:
    return "http://test"


@pytest.fixture
async def client(base_url: str):
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/v1/documents/templates
# ---------------------------------------------------------------------------


class TestTemplatesEndpoint:
    async def test_returns_list(self, client: AsyncClient):
        resp = await client.get("/api/v1/documents/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 4

    async def test_template_shape(self, client: AsyncClient):
        resp = await client.get("/api/v1/documents/templates")
        template = resp.json()[0]
        assert "document_type" in template
        assert "label" in template
        assert "description" in template
        assert "supported_deal_types" in template
        assert "supported_formats" in template
        assert "required_fields" in template

    async def test_includes_loi(self, client: AsyncClient):
        resp = await client.get("/api/v1/documents/templates")
        types = {t["document_type"] for t in resp.json()}
        assert "loi" in types
        assert "psa" in types
        assert "deal_summary" in types
        assert "proforma_spreadsheet" in types


# ---------------------------------------------------------------------------
# POST /api/v1/documents/preview
# ---------------------------------------------------------------------------


class TestPreviewEndpoint:
    async def test_preview_deal_summary(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/preview",
            json={
                "document_type": "deal_summary",
                "deal_type": "land_deal",
                "context": {
                    "property_address": "7940 Plantation Blvd, Miramar, FL 33023",
                    "zoning_district": "RS-4",
                    "max_units": 4,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_type"] == "deal_summary"
        assert data["deal_type"] == "land_deal"
        assert data["clause_count"] > 0
        assert isinstance(data["clauses"], list)
        assert len(data["clauses"]) == data["clause_count"]

    async def test_preview_clause_structure(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/preview",
            json={
                "document_type": "deal_summary",
                "deal_type": "land_deal",
                "context": {"property_address": "123 Main St, Miami, FL"},
            },
        )
        clause = resp.json()["clauses"][0]
        assert "id" in clause
        assert "title" in clause
        assert "content" in clause

    async def test_preview_loi(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/preview",
            json={
                "document_type": "loi",
                "deal_type": "land_deal",
                "context": {
                    "property_address": "456 Oak Ave, Fort Lauderdale, FL",
                    "buyer_name": "EP Ventures LLC",
                    "seller_name": "John Doe",
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_type"] == "loi"
        assert data["clause_count"] > 0

    async def test_preview_psa(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/preview",
            json={
                "document_type": "psa",
                "deal_type": "subject_to",
                "context": {
                    "property_address": "789 Pine St, Miami, FL",
                    "buyer_name": "EP Ventures LLC",
                    "seller_name": "Jane Smith",
                    "purchase_price": 350000,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_type"] == "psa"
        assert data["deal_type"] == "subject_to"
        assert data["clause_count"] > 0

    async def test_preview_invalid_document_type(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/preview",
            json={
                "document_type": "nonexistent_doc",
                "deal_type": "land_deal",
                "context": {},
            },
        )
        assert resp.status_code in (400, 422, 500)


# ---------------------------------------------------------------------------
# POST /api/v1/documents/generate
# ---------------------------------------------------------------------------


class TestGenerateEndpoint:
    async def test_generate_deal_summary_docx(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "deal_summary",
                "deal_type": "land_deal",
                "context": {
                    "property_address": "7940 Plantation Blvd, Miramar, FL 33023",
                    "zoning_district": "RS-4",
                    "max_units": 4,
                    "median_price_per_acre": 450000,
                },
            },
        )
        assert resp.status_code == 200
        assert (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            in resp.headers.get("content-type", "")
        )
        assert resp.headers.get("content-disposition", "").startswith("attachment")
        # Valid docx (ZIP format)
        assert resp.content[:4] == b"PK\x03\x04"

    async def test_generate_loi_docx(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "loi",
                "deal_type": "land_deal",
                "context": {
                    "property_address": "456 Oak Ave, Fort Lauderdale, FL",
                    "buyer_name": "EP Ventures LLC",
                    "seller_name": "John Doe",
                    "purchase_price": 250000,
                },
            },
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"PK\x03\x04"

    async def test_generate_proforma_xlsx(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "proforma_spreadsheet",
                "deal_type": "land_deal",
                "context": {
                    "property_address": "7940 Plantation Blvd, Miramar, FL",
                    "gross_development_value": 1600000,
                    "hard_costs": 800000,
                    "soft_costs": 120000,
                    "max_units": 4,
                },
            },
        )
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers.get("content-type", "")
        assert resp.content[:4] == b"PK\x03\x04"

    async def test_generate_psa_subject_to(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "psa",
                "deal_type": "subject_to",
                "context": {
                    "property_address": "789 Pine St, Miami, FL",
                    "buyer_name": "EP Ventures LLC",
                    "seller_name": "Jane Smith",
                    "purchase_price": 350000,
                    "existing_mortgage_balance_1": 280000,
                },
            },
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"PK\x03\x04"

    async def test_generate_has_content_length(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "deal_summary",
                "deal_type": "land_deal",
                "context": {"property_address": "123 Main St"},
            },
        )
        assert resp.status_code == 200
        content_length = resp.headers.get("content-length")
        assert content_length is not None
        assert int(content_length) > 0

    async def test_generate_filename_in_disposition(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "loi",
                "deal_type": "land_deal",
                "context": {"property_address": "123 Main St"},
            },
        )
        disposition = resp.headers.get("content-disposition", "")
        assert "LOI_" in disposition or "loi_" in disposition.lower()
        assert ".docx" in disposition


# ---------------------------------------------------------------------------
# Input validation — strings in numeric fields → 400 not 500
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Edge-case: Happy Path — all deal types and doc types
# ---------------------------------------------------------------------------


class TestAllDealTypesAndDocTypes:
    """Verify every deal type and document type produces valid output."""

    ALL_DEAL_TYPES = [
        "land_deal",
        "subject_to",
        "wrap",
        "seller_finance",
        "hybrid",
        "jv",
    ]
    ALL_DOC_TYPES = ["loi", "psa", "deal_summary", "proforma_spreadsheet"]

    @pytest.mark.parametrize("deal_type", ALL_DEAL_TYPES)
    async def test_all_deal_types_produce_valid_deal_summary(
        self, client: AsyncClient, deal_type: str
    ):
        """All 6 deal types produce valid deal_summary docs via /generate."""
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "deal_summary",
                "deal_type": deal_type,
                "context": {
                    "property_address": "100 Test Ave, Miami, FL 33101",
                    "zoning_district": "T6-8",
                    "max_units": 10,
                },
            },
        )
        assert resp.status_code == 200, f"deal_type={deal_type!r} returned {resp.status_code}"
        # Valid ZIP (docx)
        assert resp.content[:4] == b"PK\x03\x04"
        assert len(resp.content) > 100

    @pytest.mark.parametrize("doc_type", ALL_DOC_TYPES)
    async def test_all_doc_types_produce_valid_output(self, client: AsyncClient, doc_type: str):
        """All 4 document types produce valid binary via /generate."""
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": doc_type,
                "deal_type": "land_deal",
                "context": {
                    "property_address": "200 Doc St, Fort Lauderdale, FL 33301",
                    "buyer_name": "Test Buyer LLC",
                    "seller_name": "Test Seller",
                    "purchase_price": 500000,
                    "gross_development_value": 2000000,
                    "hard_costs": 1000000,
                    "soft_costs": 200000,
                    "max_units": 8,
                },
            },
        )
        assert resp.status_code == 200, f"doc_type={doc_type!r} returned {resp.status_code}"
        # All output formats are ZIP-based (docx, xlsx)
        assert resp.content[:4] == b"PK\x03\x04"
        assert len(resp.content) > 100

    async def test_empty_context_returns_200(self, client: AsyncClient):
        """POST /generate with context: {} returns 200 with placeholder defaults."""
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "deal_summary",
                "deal_type": "land_deal",
                "context": {},
            },
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"PK\x03\x04"

    async def test_special_characters_in_buyer_name(self, client: AsyncClient):
        """Buyer name with quotes, ampersand, angle brackets does not crash."""
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "loi",
                "deal_type": "land_deal",
                "context": {
                    "property_address": "300 Special Char Blvd, Miami, FL",
                    "buyer_name": "O'Brien & Co <LLC>",
                },
            },
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"PK\x03\x04"

    async def test_unicode_buyer_name(self, client: AsyncClient):
        """Unicode characters in buyer_name do not crash the renderer."""
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "loi",
                "deal_type": "land_deal",
                "context": {
                    "property_address": "400 Unicode Ln, Miami, FL",
                    "buyer_name": "José García",
                },
            },
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"PK\x03\x04"

    async def test_very_long_string(self, client: AsyncClient):
        """Very long buyer_name (5000 chars) does not crash the renderer."""
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "loi",
                "deal_type": "land_deal",
                "context": {
                    "property_address": "500 Long St, Miami, FL",
                    "buyer_name": "x" * 5000,
                },
            },
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"PK\x03\x04"


# ---------------------------------------------------------------------------
# Edge-case: Unhappy Path — invalid enum values
# ---------------------------------------------------------------------------


class TestInvalidEnumValues:
    """Invalid document_type or deal_type returns 400/422, not 500."""

    async def test_invalid_document_type_returns_400(self, client: AsyncClient):
        """document_type='bogus' on /preview returns 400 or 422, not 500."""
        resp = await client.post(
            "/api/v1/documents/preview",
            json={
                "document_type": "bogus",
                "deal_type": "land_deal",
                "context": {},
            },
        )
        assert resp.status_code in (400, 422), (
            f"Expected 400 or 422 for invalid document_type, got {resp.status_code}"
        )

    async def test_invalid_deal_type_returns_400(self, client: AsyncClient):
        """deal_type='bogus' on /preview returns 400 or 422, not 500."""
        resp = await client.post(
            "/api/v1/documents/preview",
            json={
                "document_type": "deal_summary",
                "deal_type": "bogus",
                "context": {},
            },
        )
        assert resp.status_code in (400, 422), (
            f"Expected 400 or 422 for invalid deal_type, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Edge-case: Preview Endpoint — clause count and financing clauses
# ---------------------------------------------------------------------------


class TestPreviewEdgeCases:
    """Verify preview clause_count consistency and financing clause presence."""

    @pytest.mark.parametrize(
        "doc_type,deal_type",
        [
            ("deal_summary", "land_deal"),
            ("loi", "subject_to"),
            ("psa", "wrap"),
            ("deal_summary", "hybrid"),
        ],
    )
    async def test_preview_returns_clause_count_matching_list(
        self, client: AsyncClient, doc_type: str, deal_type: str
    ):
        """clause_count field always matches the length of the clauses list."""
        resp = await client.post(
            "/api/v1/documents/preview",
            json={
                "document_type": doc_type,
                "deal_type": deal_type,
                "context": {
                    "property_address": "600 Count Ave, Miami, FL",
                    "buyer_name": "Counter LLC",
                    "seller_name": "Seller Inc",
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["clause_count"] == len(data["clauses"]), (
            f"clause_count={data['clause_count']} but len(clauses)={len(data['clauses'])}"
        )

    async def test_preview_psa_subject_to_has_financing_clauses(self, client: AsyncClient):
        """PSA with subject_to deal type includes financing-related clauses."""
        resp = await client.post(
            "/api/v1/documents/preview",
            json={
                "document_type": "psa",
                "deal_type": "subject_to",
                "context": {
                    "property_address": "700 Finance Rd, Miami, FL",
                    "buyer_name": "SubTo Buyer LLC",
                    "seller_name": "SubTo Seller",
                    "purchase_price": 400000,
                    "existing_mortgage_balance_1": 320000,
                    "financing_type": "subject_to",
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        clauses = data["clauses"]
        assert len(clauses) > 0

        # Check that at least one clause relates to financing / purchase price
        # The PSA subject_to clauses include purchase_price_subject_to, escrow_closing, etc.
        clause_ids = [c["id"] for c in clauses]
        clause_titles_lower = [c["title"].lower() for c in clauses]
        clause_content_lower = [c.get("content", "").lower() for c in clauses]

        has_financing = (
            any(
                "financ" in t or "subject" in t or "mortgage" in t or "purchase price" in t
                for t in clause_titles_lower
            )
            or any(
                "financ" in cid or "subject" in cid or "purchase_price" in cid for cid in clause_ids
            )
            or any("existing" in c and "mortgage" in c for c in clause_content_lower)
        )
        assert has_financing, (
            f"Expected at least one financing-related clause for PSA subject_to, "
            f"got clause ids: {clause_ids}"
        )


# ---------------------------------------------------------------------------
# Input validation — strings in numeric fields → 400 not 500
# ---------------------------------------------------------------------------


class TestInputValidation:
    async def test_string_in_purchase_price_returns_400(self, client: AsyncClient):
        """String in numeric field should return 400, not crash with 500."""
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "deal_summary",
                "deal_type": "land_deal",
                "context": {"purchase_price": "abc"},
            },
        )
        assert resp.status_code == 400

    async def test_none_in_numeric_field_returns_400(self, client: AsyncClient):
        """None in numeric field should return 400, not crash."""
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "deal_summary",
                "deal_type": "land_deal",
                "context": {"max_units": None},
            },
        )
        assert resp.status_code == 400

    async def test_list_in_numeric_field_returns_400(self, client: AsyncClient):
        """List in numeric field should return 400, not crash."""
        resp = await client.post(
            "/api/v1/documents/generate",
            json={
                "document_type": "deal_summary",
                "deal_type": "land_deal",
                "context": {"max_units": [1, 2]},
            },
        )
        assert resp.status_code == 400
