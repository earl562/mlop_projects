from __future__ import annotations

"""
Email sending via Gmail SMTP + App Password.

Replaces Resend API (which requires a verified domain) with direct SMTP
sending through Gmail's SMTP server. No OAuth, no Google Cloud Console.

Requirements:
  1. 2-Step Verification enabled on the Gmail account
  2. App Password generated at https://myaccount.google.com/apppasswords
  3. SMTP_USER and SMTP_PASSWORD set in .env

Attachments up to ~25MB (Gmail's limit) via MIME multipart.
"""

import mimetypes
import os
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import aiosmtplib
import structlog

from outreach.config import settings

logger = structlog.get_logger(__name__)


def _build_message(
    to: str,
    subject: str,
    body: str,
    attachment_path: str | None = None,
) -> MIMEMultipart:
    """Build a MIME multipart message, optionally with a file attachment."""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = to

    # Plain-text body as the first (alternative) part
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path and os.path.isfile(attachment_path):
        filename = os.path.basename(attachment_path)
        file_size = os.path.getsize(attachment_path)
        logger.info(
            "smtp_attaching_file",
            path=attachment_path,
            size_bytes=file_size,
        )

        with open(attachment_path, "rb") as f:
            file_bytes = f.read()

        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type is None:
            mime_type = "application/octet-stream"
        main_type, sub_type = mime_type.split("/", 1)

        part = MIMEBase(main_type, sub_type)
        part.set_payload(file_bytes)

        from email import encoders

        encoders.encode_base64(part)

        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=filename,
        )
        msg.attach(part)

    return msg


async def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: str | None = None,
) -> dict[str, str]:
    """
    Send an email via Gmail SMTP with App Password authentication.

    Returns {"message_id": "...", "status": "sent"} on success,
    or {"error": "...", "status": "failed"} on failure.
    """
    smtp_user = settings.smtp_user
    smtp_password = settings.smtp_password

    if not smtp_user or not smtp_password:
        logger.error("smtp_credentials_missing")
        return {"error": "smtp_credentials_not_configured", "status": "failed"}

    msg = _build_message(to, subject, body, attachment_path)

    try:
        async with aiosmtplib.SMTP(
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=True,
            timeout=30,
        ) as smtp:
            await smtp.login(smtp_user, smtp_password)
            await smtp.send_message(msg)

        message_id = msg.get("Message-ID", "") or ""
        logger.info("smtp_email_sent", to=to, subject=subject, message_id=message_id)
        return {"message_id": message_id, "status": "sent"}

    except aiosmtplib.SMTPAuthenticationError as exc:
        logger.error("smtp_auth_failed", to=to, error=str(exc))
        return {
            "error": "SMTP authentication failed — check your App Password or ensure 2-Step Verification is enabled",
            "status": "failed",
        }
    except aiosmtplib.SMTPException as exc:
        error_str = str(exc)
        if "Daily user sending quota exceeded" in error_str or "550" in error_str:
            logger.error("smtp_quota_exceeded", to=to)
            return {
                "error": "Gmail daily sending quota exceeded (500 emails/day). Try again tomorrow.",
                "status": "failed",
            }
        logger.error("smtp_send_error", to=to, error=error_str)
        return {"error": error_str, "status": "failed"}
    except Exception as exc:
        logger.error("smtp_send_exception", to=to, error=str(exc))
        return {"error": str(exc), "status": "failed"}
