# PlotLot Webhook-Based Agent Harness Integration

## Overview

This document describes how to extend PlotLot to serve as a CRM-agnostic agent harness for B2B land developer services using webhook-based integration. The approach enables any CRM system to integrate with PlotLot without requiring custom connectors, leveraging standard webhook capabilities that exist in 99% of modern CRM platforms.

## Core Concepts

### CRM-Agnostic Integration Pattern

The integration follows a standardized pattern:
1. **Tenant Setup**: One-time configuration in PlotLot for each CRM tenant
2. **CRM Configuration**: Standard webhook setup in the CRM system
3. **Execution Flow**: 
   - CRM triggers analysis via inbound webhook
   - PlotLot processes request and queues analysis job
   - PlotLot executes harness analysis pipeline
   - PlotLot sends results via outbound webhook to CRM
   - CRM processes response and updates records

### Security Model

All webhook communications are secured using:
- HMAC-SHA256 signatures for message authenticity and integrity
- Timestamp validation (5-minute window) to prevent replay attacks
- Shared secrets known only to PlotLot and the CRM

## Implementation Plan

### Phase 1: Webhook Infrastructure

#### 1.1 Create Webhook Handler Module
Create `plotlot/src/plotlot/api/webhooks.py` with:
- Inbound webhook endpoint (`/api/v1/webhooks/{tenant_id}/trigger-analysis`)
- Outbound webhook sending utility
- HMAC signature validation and generation
- Timestamp validation
- Tenant isolation

#### 1.2 Add Webhook Configuration to Settings
Extend `plotlot/src/plotlot/config.py` with:
- Webhook-specific configuration options
- Shared secret management (per-tenant)
- Webhook URL templates

#### 1.3 Create Tenant Model
Add to `plotlot/src/plotlot/storage/models.py`:
- `WebhookTenant` model to store tenant configurations
- Tenant-specific settings (shared secret, callback URL, etc.)

### Phase 2: Harness Extension for Webhook Usage

#### 2.1 Create Webhook Tool Context Extension
Extend `ToolContext` to include:
- `webhook_tenant_id`: ID of the tenant triggering the analysis
- `callback_url`: URL to send results to
- `webhook_id`: Unique identifier for this webhook exchange

#### 2.2 Create Analysis Trigger Tool
Add a new tool to the harness:
- `trigger_analysis_via_webhook`: Entry point for webhook-triggered analyses
- Validates webhook tenant and prepares execution context
- Queues the analysis job with proper tenant isolation

#### 2.3 Create Result Sending Utility
Add functionality to:
- Serve analysis results via outbound webhook
- Generate HMAC signatures for outbound requests
- Handle retries and error cases
- Update analysis run status based on webhook delivery

### Phase 3: API Endpoints

#### 3.1 Inbound Webhook Endpoint
`POST /api/v1/webhooks/{tenant_id}/trigger-analysis`
- Validates tenant exists
- Verifies timestamp and HMAC signature
- Extracts analysis parameters from payload
- Creates ToolContext with webhook information
- Queues analysis job via existing harness mechanisms
- Returns 202 Accepted with analysis ID

#### 3.2 Outbound Webhook Sender
Internal utility used by the harness to:
- Send results to CRM when analysis completes
- Include comprehensive results with evidence ledger
- Handle delivery failures and retries

### Phase 4: Data Model Extensions

#### 4.1 Webhook Tenant Model
```python
class WebhookTenant(Base):
    """CRM tenant configuration for webhook-based integration."""
    
    __tablename__ = "webhook_tenants"
    
    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(100), nullable=False, unique=True, index=True)  # External tenant ID
    name = Column(String(200), nullable=False)
    shared_secret_enc = Column(Text, nullable=False)  # Encrypted Fernet
    callback_url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

#### 4.2 Webhook Exchange Tracking
```python
class WebhookExchange(Base):
    """Tracks individual webhook exchanges for audit and debugging."""
    
    __tablename__ = "webhook_exchanges"
    
    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("webhook_tenants.id"), nullable=False, index=True)
    analysis_run_id = Column(String(36), ForeignKey("analysis_runs.id"), nullable=False, index=True)
    inbound_webhook_id = Column(String(100), nullable=True)
    outbound_webhook_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending, completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
```

### Phase 5: Harness Integration Points

#### 5.1 Analysis Run Lifecycle Hooks
Modify analysis execution to:
- Detect when triggered by webhook
- Prepare appropriate ToolContext with webhook data
- Send results via outbound webhook upon completion
- Update WebhookExchange record with outcome

#### 5.2 Error Handling and Reporting
- Send error details via webhook when analysis fails
- Include error codes and remediation suggestions
- Maintain audit trail of all webhook exchanges

## Detailed Component Design

### Webhook Handler

```python
# plotlot/src/plotlot/api/webhooks.py

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from plotlot.config import settings
from plotlot.storage.db import get_session
from plotlot.storage.models import WebhookTenant, WebhookExchange, AnalysisRun
import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

def _get_fernet():
    """Get Fernet instance for decrypting shared secrets."""
    key = settings.connector_encryption_key
    if not key:
        raise HTTPException(status_code=503, detail="Webhook system not configured")
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)

def _decrypt(fernet: Fernet, ciphertext: str) -> str:
    """Decrypt encrypted value."""
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception:
        raise HTTPException(status_code=500, detail="Decryption failed")

def _validate_webhook_request(
    tenant_id: str,
    request: Request,
    shared_secret: str,
    timestamp_header: str = "X-PlotLot-Timestamp",
    signature_header: str = "X-PlotLot-Signature"
) -> tuple[bool, str]:
    """Validate webhook request timestamp and signature."""
    # Get headers
    timestamp_str = request.headers.get(timestamp_header)
    signature = request.headers.get(signature_header)
    
    if not timestamp_str or not signature:
        return False, "Missing required headers"
    
    # Validate timestamp (within 5 minutes)
    try:
        request_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except ValueError:
        return False, "Invalid timestamp format"
    
    now = datetime.now(timezone.utc)
    if abs((now - request_time).total_seconds()) > 300:  # 5 minutes
        return False, "Timestamp outside valid window"
    
    # Get request body
    body = request.body()
    
    # Calculate expected signature
    message = f"{timestamp_str}{body.decode()}"
    expected_signature = hmac.new(
        shared_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Compare signatures (constant-time comparison)
    if not hmac.compare_digest(signature, expected_signature):
        return False, "Invalid signature"
    
    return True, ""

@router.post("/{tenant_id}/trigger-analysis")
async def trigger_analysis(
    tenant_id: str,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Handle inbound webhook from CRM to trigger analysis."""
    # Get tenant configuration
    session = await get_session()
    try:
        result = await session.execute(
            select(WebhookTenant).where(WebhookTenant.tenant_id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant or not tenant.is_active:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Decrypt shared secret
        fernet = _get_fernet()
        shared_secret = _decrypt(fernet, tenant.shared_secret_enc)
        
        # Validate webhook request
        is_valid, error_msg = _validate_webhook_request(
            tenant_id, request, shared_secret
        )
        if not is_valid:
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
            status="processing"
        )
        session.add(exchange)
        await session.flush()  # Get ID
        
        # Extract analysis parameters
        analysis_type = payload.get("analysis_type", "full_feasibility")
        property_data = payload.get("property", {})
        callback_url = payload.get("callback_url", tenant.callback_url)
        context_data = payload.get("context", {})
        
        # Queue analysis job (background task)
        background_tasks.add_task(
            process_webhook_analysis,
            tenant_id=tenant.id,
            exchange_id=str(exchange.id),
            analysis_type=analysis_type,
            property_data=property_data,
            callback_url=callback_url,
            context_data=context_data,
            payload=payload
        )
        
        return {
            "status": "accepted",
            "exchange_id": str(exchange.id),
            "message": "Analysis queued for processing"
        }
        
    finally:
        await session.close()
```

### Analysis Processing Function

```python
# plotlot/src/plotlot/api/webhooks.py (continued)

async def process_webhook_analysis(
    tenant_id: str,
    exchange_id: str,
    analysis_type: str,
    property_data: dict,
    callback_url: str,
    context_data: dict,
    payload: dict
):
    """Process analysis triggered by webhook (runs in background)."""
    from plotlot.harness.default_runtime import get_default_runtime
    from plotlot.harness.mcp_adapter import MCPAdapter
    from plotlot.land_use.models import ToolContext
    from plotlot.storage.db import get_session
    from plotlot.storage.models import WebhookExchange, AnalysisRun
    import json
    from datetime import datetime, timezone
    
    session = await get_session()
    try:
        # Get exchange record
        result = await session.execute(
            select(WebhookExchange).where(WebhookExchange.id == exchange_id)
        )
        exchange = result.scalar_one_or_none()
        
        if not exchange:
            return  # Exchange not found
        
        # Get tenant for callback URL and secret
        result = await session.execute(
            select(WebhookTenant).where(WebhookTenant.tenant_id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            exchange.status = "failed"
            exchange.error_message = "Tenant not found during processing"
            await session.commit()
            return
        
        # Prepare ToolContext for webhook-triggered analysis
        context = ToolContext(
            workspace_id=context_data.get("workspace_id", "default"),
            actor_user_id=context_data.get("user_id", "webhook_system"),
            run_id=context_data.get("run_id", f"webhook_{exchange_id}"),
            project_id=context_data.get("project_id"),
            site_id=context_data.get("site_id"),
            analysis_id=context_data.get("analysis_id"),
            analysis_run_id=None,  # Will be set after analysis starts
            risk_budget_cents=100,  # Reasonable budget for webhook analyses
            live_network_allowed=True,
            approved_approval_ids=set()
        )
        
        # Create analysis run record
        analysis_run = AnalysisRun(
            workspace_id=context.workspace_id,
            project_id=context.project_id,
            site_id=context.site_id,
            status="pending",
            input_json={
                "analysis_type": analysis_type,
                "property_data": property_data,
                "trigger_source": "webhook",
                "webhook_exchange_id": exchange_id,
                "original_payload": payload
            }
        )
        session.add(analysis_run)
        await session.flush()
        
        # Update exchange with analysis run ID
        exchange.analysis_run_id = str(analysis_run.id)
        await session.commit()
        
        # Execute analysis via harness
        adapter = MCPAdapter(get_default_runtime())
        
        # Prepare analysis arguments based on property data
        analysis_args = {
            "address": f"{property_data.get('address', '')}, {property_data.get('city', '')}, {property_data.get('state', '')} {property_data.get('zip', '')}".strip(", "),
            "analysis_type": analysis_type
        }
        
        # Add property details if available
        if property_data.get("latitude") and property_data.get("longitude"):
            analysis_args["lat"] = property_data["latitude"]
            analysis_args["lng"] = property_data["longitude"]
        
        # Call the analysis pipeline through MCP adapter
        try:
            result = await adapter.call_tool(
                name="analyze_address",  # Assuming this tool exists or we create it
                arguments=analysis_args,
                context=context
            )
            
            # Update analysis run with results
            analysis_run.status = "completed" if result.status == "ok" else "failed"
            analysis_run.output_json = result.result or {}
            analysis_run.error_message = result.message
            analysis_run.completed_at = datetime.now(timezone.utc)
            
            # Update exchange
            exchange.status = "completed" if result.status == "ok" else "failed"
            exchange.completed_at = datetime.now(timezone.utc)
            
            if result.status == "ok":
                exchange.outbound_webhook_id = f"out_{exchange_id}_{int(datetime.now().timestamp())}"
                
                # Send outbound webhook to CRM
                await _send_outbound_webhook(
                    callback_url=callback_url,
                    shared_secret=_decrypt(_get_fernet(), tenant.shared_secret_enc),
                    webhook_id=exchange.outbound_webhook_id,
                    exchange_id=exchange_id,
                    analysis_run_id=str(analysis_run.id),
                    result=result.result,
                    tenant_id=tenant_id
                )
            else:
                exchange.error_message = result.message
            
            await session.commit()
            
        except Exception as exc:
            # Handle execution errors
            analysis_run.status = "failed"
            analysis_run.error_message = str(exc)
            analysis_run.completed_at = datetime.now(timezone.utc)
            
            exchange.status = "failed"
            exchange.error_message = str(exc)
            exchange.completed_at = datetime.now(timezone.utc)
            
            await session.commit()
            
            # Try to send error webhook
            try:
                await _send_outbound_webhook(
                    callback_url=callback_url,
                    shared_secret=_decrypt(_get_fernet(), tenant.shared_secret_enc),
                    webhook_id=f"err_{exchange_id}_{int(datetime.now().timestamp())}",
                    exchange_id=exchange_id,
                    analysis_run_id=str(analysis_run.id) if analysis_run.id else None,
                    error=str(exc),
                    tenant_id=tenant_id,
                    is_error=True
                )
            except:
                pass  # Best effort to send error notification
    
    finally:
        await session.close()

async def _send_outbound_webhook(
    callback_url: str,
    shared_secret: str,
    webhook_id: str,
    exchange_id: str,
    analysis_run_id: str | None,
    result: dict | None = None,
    error: str | None = None,
    tenant_id: str = "",
    is_error: bool = False
):
    """Send outbound webhook to CRM with results or error."""
    import httpx
    from datetime import datetime, timezone
    import json
    
    # Prepare payload
    payload = {
        "webhook_id": webhook_id,
        "exchange_id": exchange_id,
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if is_error:
        payload.update({
            "status": "failed",
            "error": error,
            "analysis_id": analysis_run_id
        })
    else:
        payload.update({
            "status": "completed",
            "progress_percentage": 100,
            "result": result or {},
            "analysis_id": analysis_run_id
        })
    
    # Calculate HMAC signature
    timestamp = payload["timestamp"]
    body_json = json.dumps(payload)
    message = f"{timestamp}{body_json}"
    signature = hmac.new(
        shared_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Send webhook
    headers = {
        "Content-Type": "application/json",
        "X-PlotLot-Timestamp": timestamp,
        "X-PlotLot-Signature": signature
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(callback_url, json=payload, headers=headers)
            response.raise_for_status()
        except Exception as exc:
            # Log error but don't raise - we don't want to fail the analysis due to webhook issues
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send outbound webhook: {exc}")
```

### Tool Context Extension

Update `plotlot/src/plotlot/harness/context.py` or create a webhook-specific context extension:

```python
# In plotlot/src/plotlot/harness/context.py - extend ContextPacket or create WebhookContextPacket

@dataclass(frozen=True)
class WebhookContextPacket(ContextPacket):
    """Extended context packet for webhook-triggered analyses."""
    webhook_tenant_id: str | None = None
    callback_url: str | None = None
    webhook_id: str | None = None
    original_payload: dict[str, Any] = field(default_factory=dict)
```

### Configuration Updates

Add to `plotlot/src/plotlot/config.py`:

```python
# In Settings class
webhook_shared_secret_key: str = ""  # For encrypting tenant shared secrets
webhook_default_callback_url: str = ""  # Fallback callback URL
webhook_timeout_seconds: int = 30  # Outbound webhook timeout
webhook_max_retries: int = 3  # Max retry attempts for failed webhooks
```

## API Contracts

### Inbound Webhook Request (CRM → PlotLot)

```json
{
  "webhook_id": "wh_abc123",
  "tenant_id": "dealflow-crm-001",
  "trigger_event": "lead_status_change",
  "triggered_at": "2026-06-05T20:30:00Z",
  "triggered_by": {
    "user_id": "user_789",
    "user_email": "rep@dealflow.com",
    "user_name": "Jane Rep",
    "role": "sales_representative"
  },
  "origin_system": {
    "name": "DealFlow",
    "version": "2.1",
    "instance_url": "https://dealflow.example.com"
  },
  "property": {
    "address": "123 Main Street, Miami, FL 33101",
    "apn": "01-2345-006-0010",
    "latitude": 25.7617,
    "longitude": -80.1918,
    "jurisdiction": {
      "city": "Miami",
      "county": "Miami-Dade",
      "state": "FL",
      "country": "US"
    }
  },
  "analysis_type": "full_feasibility",
  "callback_url": "https://dealflow.example.com/api/plotlot/callback",
  "context": {
    "origin_object_type": "Lead",
    "origin_object_id": "LEAD456",
    "origin_event_id": "evt_789",
    "user_id": "user_789",
    "timestamp": "2026-06-05T20:30:00Z"
  }
}
```

### Outbound Webhook Response (PlotLot → CRM)

**Success Case:**
```json
{
  "webhook_id": "wh_def456",
  "exchange_id": "exc_xyz789",
  "tenant_id": "dealflow-crm-001",
  "timestamp": "2026-06-05T20:30:45Z",
  "status": "completed",
  "progress_percentage": 100,
  "result": {
    // Full analysis result as shown in the example
    "zoning": { ... },
    "parcel": { ... },
    "financial": { ... },
    "environmental": { ... },
    "evidence": [ ... ],
    "warnings": [ ... ],
    "metadata": { ... }
  },
  "analysis_id": "ana_xyz789"
}
```

**Error Case:**
```json
{
  "webhook_id": "wh_err123",
  "exchange_id": "exc_xyz789", 
  "tenant_id": "dealflow-crm-001",
  "timestamp": "2026-06-05T20:31:00Z",
  "status": "failed",
  "error": "Analysis failed due to insufficient zoning data",
  "analysis_id": "ana_xyz789"
}
```

## Security Considerations

### HMAC-SHA256 Implementation
- Uses shared secret known only to PlotLot and CRM
- Signature covers timestamp + request body
- Prevents tampering and replay attacks
- Industry-standard approach used by Stripe, GitHub, etc.

### Timestamp Validation
- 5-minute window prevents replay attacks
- Requires synchronized clocks (NTP recommended)
- Rejects requests with timestamps too far in past/future

### Tenant Isolation
- Each CRM gets unique tenant ID
- Separate shared secrets per tenant
- Database row-level security for tenant data
- Webhook exchanges tied to specific tenants

### Input Validation
- Strict JSON schema validation for webhook payloads
- Sanitization of all inputs to prevent injection attacks
- Size limits on payloads to prevent DoS

## Implementation Steps

### Immediate Tasks (This Sprint)

1. [ ] Create `plotlot/src/plotlot/api/webhooks.py` with inbound webhook handler
2. [ ] Add `WebhookTenant` and `WebhookExchange` models to storage models
3. [ ] Extend `Settings` with webhook configuration options
4. [ ] Create database migration for new tables
5. [ ] Implement basic outbound webhook sending utility
6. [ ] Add webhook validation utilities (HMAC, timestamp)

### Near-Term Tasks

1. [ ] Create `trigger_analysis_via_webhook` tool in harness
2. [ ] Extend `ToolContext` or create webhook-specific context
3. [ ] Integrate webhook triggering with analysis pipeline
4. [ ] Add outbound webhook sending to analysis completion flow
5. [ ] Create admin API for managing webhook tenants
6. [ ] Add webhook exchange tracking and audit capabilities

### Future Enhancements

1. [ ] Support for alternative integration patterns (REST polling, file-based)
2. [ ] Webhook delivery retry with exponential backoff
3. [ ] Detailed webhook delivery analytics and monitoring
4. [ ] Support for webhook signature versions/rotation
5. [ ] Integration with existing PlotLot authentication system
6. [ ] Webhook template customization per tenant
7. [ ] Rate limiting per webhook tenant
8. [ ] Webhook testing/debugging endpoints

## Dependencies

1. **Existing Harness Infrastructure**: Leverages existing tool registry, runtime, and MCP adapter
2. **Encryption System**: Uses existing `connector_encryption_key` for securing tenant secrets
3. **Database**: Requires new tables for tenant and exchange tracking
4. **Background Task System**: Uses FastAPI BackgroundTasks or similar for async processing
5. **HTTP Client**: Requires `httpx` for outbound webhook delivery

## Testing Strategy

### Unit Tests
- Webhook validation (timestamp, signature)
- Tenant lookup and secret decryption
- Payload parsing and validation
- Error case handling

### Integration Tests
- Full webhook exchange flow (inbound → processing → outbound)
- Database state changes during webhook processing
- Error handling and recovery scenarios
- Concurrent webhook processing

### Performance Tests
- Latency of webhook processing
- Throughput of concurrent webhook requests
- Database connection usage under load
- Memory usage during peak loads

## Deployment Considerations

### Environment Variables
- `CONNECTOR_ENCRYPTION_KEY` (required for encrypting tenant secrets)
- `WEBHOOK_TIMEOUT_SECONDS` (optional, defaults to 30s)
- `WEBHOOK_MAX_RETRIES` (optional, defaults to 3)

### Infrastructure Requirements
- PostgreSQL database (for new tables)
- Sufficient memory for concurrent webhook processing
- Outbound network connectivity for calling CRM webhooks
- Inbound network accessibility for CRM to reach PlotLot

### Monitoring and Observability
- Metrics for webhook request rates
- Latency histograms for inbound/outbound webhooks
- Error rates and failure categorization
- Audit trail of all webhook exchanges
- Integration with existing PlotLot MLflow tracing

## Comparison to Existing Patterns

### Similar to Stripe Webhook Handler
- Reuses HMAC validation pattern from `plotlot/src/plotlot/api/billing.py`
- Similar request body parsing and signature verification
- Comparable error handling and logging approaches

### Extends MCP Adapter Pattern
- Builds on existing `MCPAdapter` and `get_default_runtime()` infrastructure
- Uses same ToolContext and authorization framework
- Leverages existing tool contracts and risk assessment

### Enhances Connector Framework
- Follows same session-scoped credential pattern as email connector
- Uses similar encryption-at-rest approach for secrets
- Provides REST API surface similar to existing connectors

## Open Questions and Decisions

### 1. Tool Naming
Should we create a new `analyze_address` tool or use existing pipeline functions directly?

### 2. Analysis Identification
How should we correlate webhook exchanges with existing analysis tracking systems?

### 3. Retry Strategy
What retry policy should we use for failed outbound webhooks?

### 4. Payload Size Limits
Should we impose limits on webhook payload sizes to prevent abuse?

### 5. Admin Interface
What administrative capabilities should we provide for managing webhook tenants?

## Conclusion

This webhook-based agent harness integration provides a secure, standardized way for any CRM system to integrate with PlotLot's land analysis capabilities. By leveraging existing harness infrastructure and following proven webhook security patterns, we can deliver a robust integration that requires zero custom code on the CRM side while maintaining PlotLot's auditability, evidence standards, and reliability.

The implementation follows PlotLot's existing architectural patterns and enhances rather than replaces current functionality, ensuring backward compatibility while enabling new B2B service opportunities for land developers.