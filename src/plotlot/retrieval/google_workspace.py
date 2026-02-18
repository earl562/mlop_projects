"""Google Workspace integration — create Sheets and Docs via chat agent.

Uses raw httpx calls to Google REST APIs with OAuth2 refresh_token auth.
Zero new dependencies — just httpx (already installed).

Created documents are automatically shared with "anyone with link" access
and the URL is returned to the agent for the user.

API Reference:
  - Sheets: https://developers.google.com/sheets/api/reference/rest
  - Docs: https://developers.google.com/workspace/docs/api/reference/rest
  - Drive: https://developers.google.com/drive/api/reference/rest/v3
"""

import logging
import time
from dataclasses import dataclass

import httpx

from plotlot.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_URL = "https://oauth2.googleapis.com/token"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
DOCS_API = "https://docs.googleapis.com/v1/documents"
DRIVE_PERMISSIONS_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/permissions"

# ---------------------------------------------------------------------------
# OAuth2 token management — cache in memory, refresh automatically
# ---------------------------------------------------------------------------

_cached_token: str = ""
_token_expiry: float = 0.0


async def _get_access_token() -> str:
    """Get a valid Google OAuth2 access token, refreshing if expired.

    Caches the token in memory. Access tokens last ~3600 seconds;
    we refresh 60 seconds early to avoid edge-case expiry mid-request.
    """
    global _cached_token, _token_expiry

    if _cached_token and time.time() < _token_expiry - 60:
        return _cached_token

    if not all([settings.google_client_id, settings.google_client_secret, settings.google_refresh_token]):
        raise ValueError(
            "Google Workspace credentials not configured. "
            "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN in .env. "
            "Run scripts/setup_google_auth.py to get these values."
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": settings.google_refresh_token,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        data = resp.json()

    _cached_token = data["access_token"]
    _token_expiry = time.time() + data.get("expires_in", 3600)
    logger.info("Refreshed Google access token (expires in %ds)", data.get("expires_in", 3600))
    return _cached_token


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Drive sharing — make files accessible via link
# ---------------------------------------------------------------------------

async def _share_file(file_id: str, token: str) -> None:
    """Share a file as 'anyone with link can view'."""
    url = DRIVE_PERMISSIONS_URL.format(file_id=file_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            url,
            headers=_auth_headers(token),
            json={"type": "anyone", "role": "reader"},
        )
        resp.raise_for_status()
    logger.info("Shared file %s with 'anyone with link'", file_id)


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

@dataclass
class SpreadsheetResult:
    spreadsheet_id: str
    spreadsheet_url: str
    title: str


async def create_spreadsheet(
    title: str,
    headers: list[str],
    rows: list[list[str]],
) -> SpreadsheetResult:
    """Create a Google Sheet with headers and data rows, shared via link.

    Args:
        title: Spreadsheet title
        headers: Column header names
        rows: Data rows (each inner list is one row of string values)

    Returns:
        SpreadsheetResult with the shareable URL
    """
    token = await _get_access_token()

    # Build the sheet with data in a single create call
    all_values = [headers] + rows
    body = {
        "properties": {"title": title},
        "sheets": [{
            "properties": {"title": "Sheet1"},
            "data": [{
                "startRow": 0,
                "startColumn": 0,
                "rowData": [
                    {"values": [{"userEnteredValue": {"stringValue": str(cell)}} for cell in row]}
                    for row in all_values
                ],
            }],
        }],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(SHEETS_API, headers=_auth_headers(token), json=body)
        resp.raise_for_status()
        data = resp.json()

    spreadsheet_id = data["spreadsheetId"]
    spreadsheet_url = data["spreadsheetUrl"]

    await _share_file(spreadsheet_id, token)

    logger.info("Created spreadsheet '%s' (%d rows): %s", title, len(rows), spreadsheet_url)
    return SpreadsheetResult(
        spreadsheet_id=spreadsheet_id,
        spreadsheet_url=spreadsheet_url,
        title=title,
    )


# ---------------------------------------------------------------------------
# Google Docs
# ---------------------------------------------------------------------------

@dataclass
class DocumentResult:
    document_id: str
    document_url: str
    title: str


async def create_document(
    title: str,
    content: str,
) -> DocumentResult:
    """Create a Google Doc with text content, shared via link.

    Args:
        title: Document title
        content: Plain text content to insert

    Returns:
        DocumentResult with the shareable URL
    """
    token = await _get_access_token()

    # Step 1: Create empty document
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(DOCS_API, headers=_auth_headers(token), json={"title": title})
        resp.raise_for_status()
        doc = resp.json()

    document_id = doc["documentId"]

    # Step 2: Insert text content
    if content.strip():
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{DOCS_API}/{document_id}:batchUpdate",
                headers=_auth_headers(token),
                json={
                    "requests": [{
                        "insertText": {
                            "location": {"index": 1},
                            "text": content,
                        }
                    }]
                },
            )
            resp.raise_for_status()

    # Step 3: Share via link
    await _share_file(document_id, token)

    document_url = f"https://docs.google.com/document/d/{document_id}/edit"
    logger.info("Created document '%s': %s", title, document_url)
    return DocumentResult(
        document_id=document_id,
        document_url=document_url,
        title=title,
    )
