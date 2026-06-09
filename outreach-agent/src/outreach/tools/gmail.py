from __future__ import annotations

import base64
import json
import mimetypes
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from outreach.config import settings

logger = structlog.get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _get_credentials() -> Credentials | None:
    """Load or refresh Gmail OAuth2 credentials."""
    creds = None
    token_path = Path(settings.gmail_token_path)
    creds_path = Path(settings.gmail_credentials_path)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                logger.error("gmail_credentials_missing", path=str(creds_path))
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return creds


def _build_message(to: str, subject: str, body: str, attachment_path: str | None = None) -> dict:
    """Build a base64-encoded RFC 2822 message, optionally with an attachment."""
    if attachment_path and os.path.isfile(attachment_path):
        # Create a multipart message
        message = MIMEMultipart()
        message["to"] = to
        message["from"] = settings.outreach_from_email
        message["subject"] = subject

        # Attach the body as text
        message.attach(MIMEText(body, "plain"))

        # Attach the file
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(
                f.read(),
                Name=os.path.basename(attachment_path)
            )
        # After the file is closed
        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
        message.attach(part)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw}
    else:
        # No attachment, just plain text
        message = MIMEText(body, "plain")
        message["to"] = to
        message["from"] = settings.outreach_from_email
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw}


async def send_email(to: str, subject: str, body: str, attachment_path: str | None = None) -> dict:
    """
    Send an email via Gmail API.
    Returns {message_id, status} or {error}.
    Requires OAuth2 credentials — run `outreach gmail-auth` first.
    """
    creds = _get_credentials()
    if not creds:
        return {"error": "gmail_credentials_not_configured"}

    try:
        service = build("gmail", "v1", credentials=creds)
        msg = _build_message(to, subject, body, attachment_path)
        sent = service.users().messages().send(userId="me", body=msg).execute()
        logger.info("email_sent", to=to, subject=subject, message_id=sent.get("id"))
        return {"message_id": sent.get("id"), "status": "sent"}
    except HttpError as exc:
        logger.error("gmail_send_error", to=to, error=str(exc))
        return {"error": str(exc), "status": "failed"}


def authenticate_gmail() -> None:
    """Run OAuth2 flow interactively. Call once to generate token.json."""
    creds_path = Path(settings.gmail_credentials_path)
    if not creds_path.exists():
        print(f"[outreach] Put your Gmail OAuth credentials at: {creds_path}")
        print("[outreach] Download from: https://console.cloud.google.com/apis/credentials")
        return
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    Path(settings.gmail_token_path).write_text(creds.to_json())
    print(f"[outreach] Gmail authenticated. Token saved to {settings.gmail_token_path}")
