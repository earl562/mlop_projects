"""SMTP Email Connector — session-scoped outreach gateway.

No Google Cloud Console required. Works with any SMTP provider via App Passwords.
Credentials are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256).

Endpoints:
    POST /api/v1/connectors/email/configure   — save/update SMTP credentials
    GET  /api/v1/connectors/email/status      — check if configured for this session
    POST /api/v1/connectors/email/test        — send a test email
    POST /api/v1/connectors/email/draft       — LLM-generated outreach draft
    POST /api/v1/connectors/email/send        — send email to property owner
    DELETE /api/v1/connectors/email/disconnect — remove credentials
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.api.middleware import RateLimiter
from plotlot.config import settings
from plotlot.storage.db import get_session
from plotlot.storage.models import ConnectorCredential
from plotlot.security.context import current_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/connectors/email", tags=["connectors"])

# Tighter rate limiter for /send — 5 emails per hour per session
_send_rate_limiter = RateLimiter(max_requests=5, window_seconds=3600)

# Daily send cap per session before we stop without checking Gmail's own quota
_DAILY_SESSION_CAP = 50

SMTP_PRESETS: dict[str, dict[str, Any]] = {
    "gmail": {"host": "smtp.gmail.com", "port": 587},
    "outlook": {"host": "smtp.office365.com", "port": 587},
    "yahoo": {"host": "smtp.mail.yahoo.com", "port": 587},
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EmailConfigRequest(BaseModel):
    provider: str = Field(..., description="gmail | outlook | yahoo | custom")
    smtp_host: str | None = Field(None, description="Required when provider=custom")
    smtp_port: int = Field(587)
    smtp_username: EmailStr
    smtp_password: str = Field(..., min_length=1)
    from_name: str | None = None


class EmailConfigResponse(BaseModel):
    configured: bool
    provider_hint: str
    from_name: str | None
    smtp_username: str


class EmailStatusResponse(BaseModel):
    configured: bool
    smtp_username: str | None = None
    from_name: str | None = None
    provider_hint: str | None = None
    daily_sends_used: int = 0
    daily_sends_remaining: int = _DAILY_SESSION_CAP


class DraftRequest(BaseModel):
    owner_name: str
    property_address: str
    zoning_district: str | None = None
    max_units: int | None = None
    offer_price: float | None = None
    sender_name: str | None = None
    custom_notes: str | None = None


class DraftResponse(BaseModel):
    subject: str
    body_html: str
    body_text: str


class SendRequest(BaseModel):
    to_email: EmailStr
    to_name: str | None = None
    subject: str = Field(..., min_length=1, max_length=200)
    body_html: str = Field(..., min_length=1)
    body_text: str | None = None


class SendResponse(BaseModel):
    sent: bool
    message_id: str | None = None
    daily_sends_used: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_fernet() -> Fernet:
    key = settings.connector_encryption_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email connector is not configured on this server (missing CONNECTOR_ENCRYPTION_KEY).",
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invalid CONNECTOR_ENCRYPTION_KEY — re-generate with Fernet.generate_key().",
        )


def _encrypt(fernet: Fernet, plaintext: str) -> str:
    return fernet.encrypt(plaintext.encode()).decode()


def _decrypt(fernet: Fernet, ciphertext: str) -> str:
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Credential decryption failed — the encryption key may have rotated.",
        ) from exc


def _session_id(request: Request) -> str:
    """Extract the backend session ID from the request header."""
    sid = request.headers.get("X-Session-ID") or request.headers.get("x-session-id")
    if not sid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Session-ID header is required for connector operations.",
        )
    return sid[:128]  # Guard against pathologically long values


def _provider_hint(host: str) -> str:
    for provider, preset in SMTP_PRESETS.items():
        if preset["host"] in host:
            return provider
    return "custom"


def _reset_daily_count_if_needed(cred: ConnectorCredential) -> ConnectorCredential:
    """Reset the daily counter when the 24-hour window has elapsed."""
    now = datetime.now(timezone.utc)
    reset_at = cred.send_count_reset_at
    if reset_at is None or (now - reset_at) > timedelta(hours=24):
        cred.daily_send_count = 0
        cred.send_count_reset_at = now
    return cred


async def _get_credential(session_id: str, db: AsyncSession) -> ConnectorCredential | None:
    result = await db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.workspace_id == current_tenant_id(),
            ConnectorCredential.session_id == session_id,
        )
    )
    return result.scalar_one_or_none()


async def _send_smtp(
    cred: ConnectorCredential,
    smtp_password: str,
    to_email: str,
    to_name: str | None,
    subject: str,
    body_html: str,
    body_text: str | None,
) -> str:
    """Send via SMTP and return the Message-ID header."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    from_header = (
        f"{cred.from_name} <{cred.smtp_username}>" if cred.from_name else cred.smtp_username
    )
    msg["From"] = from_header
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email

    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        async with aiosmtplib.SMTP(
            hostname=cred.smtp_host,
            port=cred.smtp_port,
            start_tls=True,
            timeout=20,
        ) as smtp:
            await smtp.login(cred.smtp_username, smtp_password)
            await smtp.send_message(msg)
    except aiosmtplib.SMTPAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"SMTP authentication failed — check your App Password: {exc}",
        ) from exc
    except aiosmtplib.SMTPException as exc:
        error_str = str(exc)
        # Surface Gmail's daily-quota error so users understand what happened
        if "Daily user sending quota exceeded" in error_str or "550" in error_str:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Gmail daily sending quota exceeded (500 emails/day). Try again tomorrow.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SMTP error: {exc}",
        ) from exc

    return msg.get("Message-ID") or ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/configure", response_model=EmailConfigResponse)
async def configure_email(
    body: EmailConfigRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> EmailConfigResponse:
    """Save or update SMTP credentials for this session."""
    session_id = _session_id(request)
    fernet = _get_fernet()

    if body.provider != "custom":
        preset = SMTP_PRESETS.get(body.provider)
        if not preset:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown provider '{body.provider}'. Use: gmail, outlook, yahoo, custom.",
            )
        smtp_host = preset["host"]
        smtp_port = preset["port"]
    else:
        if not body.smtp_host:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="smtp_host is required when provider=custom.",
            )
        smtp_host = body.smtp_host
        smtp_port = body.smtp_port

    encrypted_pw = _encrypt(fernet, body.smtp_password)

    cred = await _get_credential(session_id, db)
    if cred:
        cred.smtp_host = smtp_host
        cred.smtp_port = smtp_port
        cred.smtp_username = str(body.smtp_username)
        cred.smtp_password_enc = encrypted_pw
        cred.from_name = body.from_name
    else:
        cred = ConnectorCredential(
            workspace_id=current_tenant_id(),
            session_id=session_id,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_username=str(body.smtp_username),
            smtp_password_enc=encrypted_pw,
            from_name=body.from_name,
        )
        db.add(cred)

    await db.commit()
    logger.info("Email connector configured for session %s...", session_id[:8])

    return EmailConfigResponse(
        configured=True,
        provider_hint=_provider_hint(smtp_host),
        from_name=body.from_name,
        smtp_username=str(body.smtp_username),
    )


@router.get("/status", response_model=EmailStatusResponse)
async def email_status(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> EmailStatusResponse:
    """Return connector status for this session — no credentials exposed."""
    session_id = _session_id(request)
    cred = await _get_credential(session_id, db)

    if not cred:
        return EmailStatusResponse(configured=False)

    cred = _reset_daily_count_if_needed(cred)
    return EmailStatusResponse(
        configured=True,
        smtp_username=cred.smtp_username,
        from_name=cred.from_name,
        provider_hint=_provider_hint(cred.smtp_host),
        daily_sends_used=cred.daily_send_count,
        daily_sends_remaining=max(0, _DAILY_SESSION_CAP - cred.daily_send_count),
    )


@router.post("/test", response_model=SendResponse)
async def test_email(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> SendResponse:
    """Send a test email to confirm SMTP credentials work."""
    session_id = _session_id(request)
    fernet = _get_fernet()
    cred = await _get_credential(session_id, db)

    if not cred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No email connector configured for this session. Call /configure first.",
        )

    smtp_password = _decrypt(fernet, cred.smtp_password_enc)
    message_id = await _send_smtp(
        cred=cred,
        smtp_password=smtp_password,
        to_email=cred.smtp_username,
        to_name=cred.from_name,
        subject="PlotLot — Email connector test",
        body_html=(
            "<p>Your PlotLot email connector is working correctly.</p>"
            "<p>You can now send outreach emails to property owners from the Outreach tab.</p>"
        ),
        body_text="Your PlotLot email connector is working correctly.",
    )

    return SendResponse(sent=True, message_id=message_id, daily_sends_used=cred.daily_send_count)


@router.post("/draft", response_model=DraftResponse)
async def draft_email(
    body: DraftRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> DraftResponse:
    """Generate an outreach email draft with Claude Sonnet."""
    session_id = _session_id(request)
    cred = await _get_credential(session_id, db)

    # Validate session is connected (draft doesn't send, but gating on config
    # ensures the user has thought through their sender identity)
    if not cred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configure the email connector before generating drafts.",
        )

    import anthropic

    sender = body.sender_name or (cred.from_name if cred.from_name else "a local investor")

    prompt_parts = [
        f"Property address: {body.property_address}",
        f"Owner name: {body.owner_name}",
    ]
    if body.zoning_district:
        prompt_parts.append(f"Zoning district: {body.zoning_district}")
    if body.max_units is not None:
        prompt_parts.append(f"Max allowable units: {body.max_units}")
    if body.offer_price is not None:
        prompt_parts.append(f"Estimated offer price: ${body.offer_price:,.0f}")
    if body.custom_notes:
        prompt_parts.append(f"Sender notes: {body.custom_notes}")

    property_context = "\n".join(prompt_parts)

    system_prompt = (
        "You are an expert real estate investor writing a direct-mail outreach letter to a property owner. "
        "The letter should be professional, warm, and concise — no more than 150 words. "
        "Lead with the property address. Mention you are interested in purchasing. "
        "Do NOT make an explicit offer price unless provided. Do NOT use legal jargon. "
        "Close with the sender's contact info placeholder [PHONE] and [EMAIL]. "
        "Return a JSON object with keys: subject (string), body_html (HTML string), body_text (plain text string). "
        "body_html should wrap paragraphs in <p> tags. No markdown."
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Write an outreach email from {sender} about this property:\n\n"
                        f"{property_context}"
                    ),
                }
            ],
        )
    except Exception as exc:
        logger.error("Anthropic API error during draft generation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Draft generation failed: {exc}",
        ) from exc

    first_block = response.content[0]
    if not hasattr(first_block, "text"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Draft generation returned unexpected content block type",
        )
    raw = first_block.text.strip()

    # Strip markdown code fences if model wrapped JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    import json

    try:
        parsed = json.loads(raw)
        return DraftResponse(
            subject=parsed["subject"],
            body_html=parsed["body_html"],
            body_text=parsed["body_text"],
        )
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Draft JSON parse failed: %s | raw: %s", exc, raw[:200])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Draft generation returned unexpected format. Please try again.",
        ) from exc


@router.post("/send", response_model=SendResponse)
async def send_email(
    body: SendRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> SendResponse:
    """Send an outreach email to a single recipient."""
    # Tight rate limit: 5 per hour per session
    await _send_rate_limiter.check(request)

    session_id = _session_id(request)
    fernet = _get_fernet()
    cred = await _get_credential(session_id, db)

    if not cred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No email connector configured. Call /configure first.",
        )

    # Reset daily counter if the 24-hour window has passed
    cred = _reset_daily_count_if_needed(cred)

    if cred.daily_send_count >= _DAILY_SESSION_CAP:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily session send limit reached ({_DAILY_SESSION_CAP} emails/day). Resets in 24 hours.",
        )

    smtp_password = _decrypt(fernet, cred.smtp_password_enc)
    message_id = await _send_smtp(
        cred=cred,
        smtp_password=smtp_password,
        to_email=str(body.to_email),
        to_name=body.to_name,
        subject=body.subject,
        body_html=body.body_html,
        body_text=body.body_text,
    )

    cred.daily_send_count += 1
    await db.commit()

    logger.info(
        "Outreach email sent: session=%s... to=%s subject=%s",
        session_id[:8],
        body.to_email,
        body.subject[:40],
    )

    return SendResponse(
        sent=True,
        message_id=message_id,
        daily_sends_used=cred.daily_send_count,
    )


@router.delete("/disconnect", status_code=204)
async def disconnect_email(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> None:
    """Remove SMTP credentials for this session."""
    session_id = _session_id(request)
    cred = await _get_credential(session_id, db)

    if cred:
        await db.delete(cred)
        await db.commit()
        logger.info("Email connector disconnected for session %s...", session_id[:8])
