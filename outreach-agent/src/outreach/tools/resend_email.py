from __future__ import annotations

"""
Email sending via Resend.com API.

Replaces Gmail API OAuth with a simple API key.
No credentials.json, no token.json, no Google Cloud Console setup needed.

Usage:
  1. Sign up at https://resend.com (free tier: 3,000 emails/month)
  2. Create an API key in the Resend dashboard
  3. Set RESEND_API_KEY in .env or environment
  4. Set RESEND_FROM_EMAIL (use onboarding@resend.dev to test, or verify a domain)

Attachments up to ~10MB base64-encoded.
"""

import base64
import os

import httpx
import structlog

from outreach.config import settings

logger = structlog.get_logger(__name__)

RESEND_API_BASE = "https://api.resend.com"


async def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: str | None = None,
) -> dict:
    """
    Send an email via Resend API.

    Returns {"id": "...", "status": "sent"} on success,
    or {"error": "...", "status": "failed"} on failure.
    """
    api_key = settings.resend_api_key
    if not api_key:
        logger.error("resend_api_key_missing")
        return {"error": "resend_api_key_not_configured", "status": "failed"}

    payload: dict = {
        "from": settings.resend_from_email,
        "to": [to],
        "subject": subject,
        "text": body,
    }

    # Attach file if it exists
    if attachment_path and os.path.isfile(attachment_path):
        file_size = os.path.getsize(attachment_path)
        logger.info(
            "resend_attaching_file",
            path=attachment_path,
            size_bytes=file_size,
        )
        with open(attachment_path, "rb") as f:
            file_bytes = f.read()
        payload["attachments"] = [
            {
                "filename": os.path.basename(attachment_path),
                "content": base64.b64encode(file_bytes).decode(),
            }
        ]

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{RESEND_API_BASE}/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            data = response.json()

        if response.status_code == 200:
            email_id = data.get("id")
            logger.info("resend_email_sent", to=to, subject=subject, email_id=email_id)
            return {"id": email_id, "status": "sent"}
        else:
            error_msg = (
                data.get("message")
                or data.get("error")
                or str(data)
            )
            logger.error(
                "resend_send_error",
                to=to,
                status_code=response.status_code,
                error=error_msg,
            )
            return {
                "error": error_msg,
                "status": "failed",
                "status_code": response.status_code,
            }

    except httpx.TimeoutException:
        logger.error("resend_timeout", to=to)
        return {"error": "request_timeout", "status": "failed"}
    except Exception as exc:
        logger.error("resend_send_exception", to=to, error=str(exc))
        return {"error": str(exc), "status": "failed"}
