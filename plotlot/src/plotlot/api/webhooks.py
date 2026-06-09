"""Webhook-based agent harness integration for CRM-agnostic connectivity."""

from __future__ import annotations

import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from sqlalchemy import select
from cryptography.fernet import Fernet

from plotlot.config import settings
from plotlot.storage.db import get_session
from plotlot.storage.models import WebhookTenant, WebhookExchange, AnalysisRun

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _get_fernet() -> Fernet:
    """Get Fernet instance for decrypting shared secrets."""
    key = settings.connector_encryption_key
    if not key:
        raise HTTPException(
            status_code=503, detail="Webhook system not configured (missing connector_encryption_key)"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def _decrypt(fernet: Fernet, ciphertext: str) -> str:
    """Decrypt an encrypted value."""
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception:
        raise HTTPException(status_code=500, detail="Decryption failed")


def _validate_webhook_request(
    request: Request,
    shared_secret: str,
    timestamp_header: str = "X-PlotLot-Timestamp",
    signature_header: str = "X-PlotLot-Signature",
) -> tuple[bool, str]:
    """Validate webhook request timestamp and HMAC-SHA256 signature."""
    timestamp_str = request.headers.get(timestamp_header)
    signature = request.headers.get(signature_header)

    if not timestamp_str or not signature:
        return False, "Missing required webhook headers"

    # Validate timestamp (within configured window)
    try:
        request_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except ValueError:
        return False, "Invalid timestamp format"

    now = datetime.now(timezone.utc)
    tolerance = settings.webhook_timestamp_tolerance_seconds
    if abs((now - request_time).total_seconds()) > tolerance:
        return False, f"Timestamp outside valid window (±{tolerance}s)"

    # Get request body for HMAC verification
    body = request.body()

    message = f"{timestamp_str}{body.decode()}"
    expected_signature = hmac.new(
        shared_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return False, "Invalid signature"

    return True, ""


def _generate_hmac_signature(shared_secret: str, timestamp: str, body: str) -> str:
    """Generate HMAC-SHA256 signature for outbound webhook."""
    message = f"{timestamp}{body}"
    return hmac.new(
        shared_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()


@router.post("/{tenant_id}/trigger-analysis")
async def trigger_analysis(
    tenant_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Handle inbound webhook from CRM to trigger analysis.

    CRM sends POST with property data and analysis type. PlotLot queues
    the analysis and returns 202 Accepted immediately. Results are sent
    back via outbound webhook when complete.
    """
    session = await get_session()
    try:
        result = await session.execute(
            select(WebhookTenant).where(
                WebhookTenant.tenant_id == tenant_id,
                WebhookTenant.is_active == True,
            )
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found or inactive")

        # Decrypt shared secret and validate request
        fernet = _get_fernet()
        shared_secret = _decrypt(fernet, tenant.shared_secret_enc)

        is_valid, error_msg = _validate_webhook_request(request, shared_secret)
        if not is_valid:
            logger.warning("Webhook validation failed for tenant %s: %s", tenant_id, error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        # Parse request body
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        # Create webhook exchange record
        exchange = WebhookExchange(
            tenant_id=tenant.id,
            inbound_webhook_id=payload.get("webhook_id"),
            status="processing",
        )
        session.add(exchange)
        await session.flush()

        # Extract analysis parameters
        analysis_type = payload.get("analysis_type", "full_feasibility")
        property_data = payload.get("property", {})
        callback_url = payload.get("callback_url", tenant.callback_url)
        context_data = payload.get("context", {})

        # Queue analysis as background task
        background_tasks.add_task(
            _process_webhook_analysis,
            tenant_id=tenant.id,
            exchange_id=str(exchange.id),
            analysis_type=analysis_type,
            property_data=property_data,
            callback_url=callback_url,
            context_data=context_data,
            payload=payload,
            shared_secret=shared_secret,
        )

        return {
            "status": "accepted",
            "exchange_id": str(exchange.id),
            "message": "Analysis queued for processing",
        }

    finally:
        await session.close()


async def _process_webhook_analysis(
    tenant_id: str,
    exchange_id: str,
    analysis_type: str,
    property_data: dict,
    callback_url: str,
    context_data: dict,
    payload: dict,
    shared_secret: str,
):
    """Execute analysis triggered by webhook (runs in background)."""
    session = await get_session()
    try:
        # Get exchange record
        result = await session.execute(
            select(WebhookExchange).where(WebhookExchange.id == exchange_id)
        )
        exchange = result.scalar_one_or_none()
        if not exchange:
            logger.error("Webhook exchange %s not found during processing", exchange_id)
            return

        # Resolve tenant for callback URL
        tenant_result = await session.execute(
            select(WebhookTenant).where(WebhookTenant.id == tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            exchange.status = "failed"
            exchange.error_message = "Tenant not found during processing"
            await session.commit()
            return

        # Extract address from property data
        address = property_data.get("address", "")
        city = property_data.get("city", "")
        state = property_data.get("state", "")
        zip_code = property_data.get("zip", "")
        full_address = f"{address}, {city}, {state} {zip_code}".strip(", ")

        if not full_address:
            exchange.status = "failed"
            exchange.error_message = "No address provided in property data"
            exchange.completed_at = datetime.now(timezone.utc)
            await session.commit()
            await _send_outbound_webhook(
                callback_url=callback_url,
                shared_secret=shared_secret,
                exchange_id=exchange_id,
                tenant_id=tenant.tenant_id,
                error="Missing address in inbound payload",
                is_error=True,
            )
            return

        # Create analysis run via existing harness pipeline
        # Use the existing /analyze SSE pipeline by calling it internally
        from plotlot.pipeline.lookup import lookup_address

        try:
            # Run the analysis pipeline
            pipeline_result = await lookup_address(
                address=full_address,
            )

            # Update analysis run record
            analysis_run = AnalysisRun(
                workspace_id=context_data.get("workspace_id", "default"),
                project_id=context_data.get("project_id"),
                site_id=context_data.get("site_id"),
                skill_name=analysis_type,
                status="completed",
                input_json={
                    "address": full_address,
                    "analysis_type": analysis_type,
                    "trigger_source": "webhook",
                    "webhook_exchange_id": exchange_id,
                },
                output_json=pipeline_result if isinstance(pipeline_result, dict) else {},
            )
            session.add(analysis_run)
            await session.flush()

            exchange.analysis_run_id = str(analysis_run.id)
            exchange.status = "completed"
            exchange.outbound_webhook_id = f"out_{exchange_id}_{int(datetime.now().timestamp())}"
            exchange.completed_at = datetime.now(timezone.utc)
            await session.commit()

            # Send results back via outbound webhook
            await _send_outbound_webhook(
                callback_url=callback_url,
                shared_secret=shared_secret,
                webhook_id=exchange.outbound_webhook_id,
                exchange_id=exchange_id,
                analysis_run_id=str(analysis_run.id),
                result=pipeline_result,
                tenant_id=tenant.tenant_id,
            )

        except Exception as exc:
            logger.error("Analysis execution failed for exchange %s: %s", exchange_id, exc)
            analysis_run = AnalysisRun(
                workspace_id=context_data.get("workspace_id", "default"),
                project_id=context_data.get("project_id"),
                site_id=context_data.get("site_id"),
                skill_name=analysis_type,
                status="failed",
                input_json={
                    "address": full_address,
                    "analysis_type": analysis_type,
                    "trigger_source": "webhook",
                    "webhook_exchange_id": exchange_id,
                },
                error_message=str(exc),
            )
            session.add(analysis_run)
            await session.flush()

            exchange.analysis_run_id = str(analysis_run.id)
            exchange.status = "failed"
            exchange.error_message = str(exc)
            exchange.completed_at = datetime.now(timezone.utc)
            await session.commit()

            # Send error notification via webhook
            try:
                await _send_outbound_webhook(
                    callback_url=callback_url,
                    shared_secret=shared_secret,
                    webhook_id=f"err_{exchange_id}_{int(datetime.now().timestamp())}",
                    exchange_id=exchange_id,
                    analysis_run_id=str(analysis_run.id),
                    error=str(exc),
                    tenant_id=tenant.tenant_id,
                    is_error=True,
                )
            except Exception as send_exc:
                logger.error(
                    "Failed to send error webhook for exchange %s: %s", exchange_id, send_exc
                )

    finally:
        await session.close()


async def _send_outbound_webhook(
    callback_url: str,
    shared_secret: str,
    exchange_id: str,
    tenant_id: str,
    webhook_id: str | None = None,
    analysis_run_id: str | None = None,
    result: dict | None = None,
    error: str | None = None,
    is_error: bool = False,
    max_retries: int = 3,
):
    """Send outbound webhook to CRM with results or error notification."""
    timestamp = datetime.now(timezone.utc).isoformat()
    webhook_id = webhook_id or f"wh_{exchange_id}"

    payload = {
        "webhook_id": webhook_id,
        "exchange_id": exchange_id,
        "tenant_id": tenant_id,
        "timestamp": timestamp,
    }

    if is_error:
        payload.update({
            "status": "failed",
            "error": error,
        })
        if analysis_run_id:
            payload["analysis_id"] = analysis_run_id
    else:
        payload.update({
            "status": "completed",
            "progress_percentage": 100,
            "result": result or {},
        })
        if analysis_run_id:
            payload["analysis_id"] = analysis_run_id

    body_json = json.dumps(payload)
    signature = _generate_hmac_signature(shared_secret, timestamp, body_json)

    headers = {
        "Content-Type": "application/json",
        settings.webhook_signature_header: signature,
        settings.webhook_timestamp_header: timestamp,
    }

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    callback_url,
                    content=body_json,
                    headers=headers,
                )
                if resp.status_code < 400:
                    logger.info(
                        "Outbound webhook sent successfully to %s (attempt %d, status %d)",
                        callback_url, attempt, resp.status_code
                    )
                    return
                else:
                    logger.warning(
                        "Outbound webhook returned %d to %s (attempt %d)",
                        resp.status_code, callback_url, attempt
                    )
                    last_exc = HTTPException(
                        status_code=resp.status_code,
                        detail=f"Webhook returned {resp.status_code}: {resp.text[:200]}",
                    )
        except Exception as exc:
            logger.warning("Outbound webhook failed to %s (attempt %d): %s", callback_url, attempt, exc)
            last_exc = exc

    logger.error(
        "Outbound webhook failed after %d attempts to %s: %s",
        max_retries, callback_url, last_exc
    )
