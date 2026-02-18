"""Unit tests for Google Workspace integration (Sheets/Docs creation).

All Google API calls are mocked — no real credentials or network needed.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import plotlot.retrieval.google_workspace as gw
from plotlot.retrieval.google_workspace import (
    _get_access_token,
    create_document,
    create_spreadsheet,
)


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """Reset the cached token before each test."""
    gw._cached_token = ""
    gw._token_expiry = 0.0
    yield
    gw._cached_token = ""
    gw._token_expiry = 0.0


@pytest.fixture
def mock_settings():
    """Provide mock Google credentials."""
    with patch("plotlot.retrieval.google_workspace.settings") as mock:
        mock.google_client_id = "test-client-id"
        mock.google_client_secret = "test-client-secret"
        mock.google_refresh_token = "test-refresh-token"
        yield mock


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_refresh_token_success(self, mock_settings):
        """Fresh token is fetched when cache is empty."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "fresh-token", "expires_in": 3600}
        mock_resp.raise_for_status = MagicMock()

        with patch("plotlot.retrieval.google_workspace.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            token = await _get_access_token()
            assert token == "fresh-token"
            assert gw._cached_token == "fresh-token"

    @pytest.mark.asyncio
    async def test_cached_token_reused(self, mock_settings):
        """Cached token is returned when not expired."""
        gw._cached_token = "cached-token"
        gw._token_expiry = time.time() + 3600

        token = await _get_access_token()
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_missing_credentials_raises(self):
        """Missing credentials raise ValueError."""
        with patch("plotlot.retrieval.google_workspace.settings") as mock:
            mock.google_client_id = ""
            mock.google_client_secret = ""
            mock.google_refresh_token = ""
            with pytest.raises(ValueError, match="credentials not configured"):
                await _get_access_token()


# ---------------------------------------------------------------------------
# Spreadsheet creation
# ---------------------------------------------------------------------------


class TestCreateSpreadsheet:
    @pytest.mark.asyncio
    async def test_create_success(self, mock_settings):
        """Creates spreadsheet and shares it."""
        create_resp = MagicMock()
        create_resp.json.return_value = {
            "spreadsheetId": "abc123",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/abc123",
        }
        create_resp.raise_for_status = MagicMock()

        share_resp = MagicMock()
        share_resp.raise_for_status = MagicMock()

        with patch("plotlot.retrieval.google_workspace._get_access_token", new_callable=AsyncMock, return_value="test-token"):
            with patch("plotlot.retrieval.google_workspace.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(side_effect=[create_resp, share_resp])
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await create_spreadsheet(
                    title="Test Sheet",
                    headers=["Address", "Zoning"],
                    rows=[["123 Main St", "R-1"], ["456 Oak Ave", "R-2"]],
                )

                assert result.spreadsheet_id == "abc123"
                assert result.title == "Test Sheet"
                assert "abc123" in result.spreadsheet_url


# ---------------------------------------------------------------------------
# Document creation
# ---------------------------------------------------------------------------


class TestCreateDocument:
    @pytest.mark.asyncio
    async def test_create_success(self, mock_settings):
        """Creates document, inserts text, and shares it."""
        create_resp = MagicMock()
        create_resp.json.return_value = {"documentId": "doc456"}
        create_resp.raise_for_status = MagicMock()

        batch_resp = MagicMock()
        batch_resp.raise_for_status = MagicMock()

        share_resp = MagicMock()
        share_resp.raise_for_status = MagicMock()

        with patch("plotlot.retrieval.google_workspace._get_access_token", new_callable=AsyncMock, return_value="test-token"):
            with patch("plotlot.retrieval.google_workspace.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(side_effect=[create_resp, batch_resp, share_resp])
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await create_document(
                    title="Test Doc",
                    content="This is a test document about R-1 zoning.",
                )

                assert result.document_id == "doc456"
                assert result.title == "Test Doc"
                assert "doc456" in result.document_url
