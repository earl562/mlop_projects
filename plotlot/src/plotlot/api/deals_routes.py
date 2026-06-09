"""Acquisition deal management, pipeline, outreach, and CRM sync routes."""

import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.db import get_session
from plotlot.storage.models import (
    ConnectorAccount,
    ConnectorSyncSettings,
    Deal,
    DealStageHistory,
    Document,
    OutreachActivity,
)

router = APIRouter(prefix="/api/v1", tags=["acquisition"])

VALID_TRANSITIONS: dict[str, list[str]] = {
    "lead": ["contacted", "lost"],
    "contacted": ["qualified", "lost"],
    "qualified": ["site_visit_scheduled", "lost"],
    "site_visit_scheduled": ["site_visit_completed", "lost"],
    "site_visit_completed": ["underwriting", "lost"],
    "underwriting": ["loi_submitted", "lost"],
    "loi_submitted": ["loi_accepted", "lost"],
    "loi_accepted": ["psa_submitted", "lost"],
    "psa_submitted": ["psa_executed", "lost"],
    "psa_executed": ["due_diligence", "lost"],
    "due_diligence": ["closing", "lost"],
    "closing": ["won", "lost"],
}

PIPELINE_STAGES = [
    "lead",
    "contacted",
    "qualified",
    "site_visit_scheduled",
    "site_visit_completed",
    "underwriting",
    "loi_submitted",
    "loi_accepted",
    "psa_submitted",
    "psa_executed",
    "due_diligence",
    "closing",
    "won",
    "lost",
]


# ---------------------------------------------------------------------------
# Pydantic schemas (inlined to avoid circular deps with api.schemas)
# ---------------------------------------------------------------------------

class DealCreateResponse:
    pass


# We'll use plain dict responses for now to keep the file self-contained
# In production, these would be proper Pydantic BaseModel classes


# ---------------------------------------------------------------------------
# Deal CRUD
# ---------------------------------------------------------------------------

@router.get("/deals")
async def list_deals(
    workspace_id: str | None = None,
    stage: str | None = None,
    status: str = "active",
    owner: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    """List deals with optional filtering."""
    stmt = select(Deal).where(Deal.is_deleted == False)  # noqa: E712
    if workspace_id:
        stmt = stmt.where(Deal.workspace_id == workspace_id)
    if stage:
        stmt = stmt.where(Deal.stage == stage)
    if status:
        stmt = stmt.where(Deal.status == status)
    if owner:
        stmt = stmt.where(Deal.owner_name.ilike(f"%{owner}%"))
    stmt = stmt.order_by(desc(Deal.updated_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    deals = result.scalars().all()
    return {
        "items": [_deal_to_dict(d) for d in deals],
        "total": len(deals),
        "limit": limit,
        "offset": offset,
    }


@router.post("/deals", status_code=201)
async def create_deal(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_session),
):
    """Create a new deal in the lead stage."""
    required = ["workspace_id", "project_id", "title", "property_address"]
    for field in required:
        if not payload.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    deal = Deal(
        workspace_id=payload["workspace_id"],
        project_id=payload["project_id"],
        site_id=payload.get("site_id"),
        title=payload["title"],
        description=payload.get("description"),
        deal_type=payload.get("deal_type", "acquisition"),
        property_address=payload["property_address"],
        owner_name=payload.get("owner_name"),
        owner_email=payload.get("owner_email"),
        owner_phone=payload.get("owner_phone"),
        asking_price=payload.get("asking_price"),
        offer_price=payload.get("offer_price"),
        stage="lead",
        status="active",
        stage_entered_at=datetime.datetime.now(datetime.timezone.utc),
        assigned_to_user_id=payload.get("assigned_to_user_id"),
        created_by_user_id=payload.get("created_by_user_id"),
        source=payload.get("source", "manual"),
        source_detail=payload.get("source_detail"),
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    return _deal_to_dict(deal)


@router.get("/deals/{deal_id}")
async def get_deal(
    deal_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Get a single deal with outreach activities."""
    deal = await _get_deal_or_404(deal_id, db)
    outreach_result = await db.execute(
        select(OutreachActivity)
        .where(OutreachActivity.deal_id == deal_id)
        .order_by(desc(OutreachActivity.created_at))
    )
    activities = outreach_result.scalars().all()
    history_result = await db.execute(
        select(DealStageHistory)
        .where(DealStageHistory.deal_id == deal_id)
        .order_by(desc(DealStageHistory.transitioned_at))
    )
    history = history_result.scalars().all()
    data = _deal_to_dict(deal)
    data["outreach_activities"] = [_outreach_to_dict(a) for a in activities]
    data["stage_history"] = [_history_to_dict(h) for h in history]
    return data


@router.put("/deals/{deal_id}")
async def update_deal(
    deal_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_session),
):
    """Update deal fields (soft update, no transitions)."""
    deal = await _get_deal_or_404(deal_id, db)
    allowed_fields = [
        "title", "description", "property_address", "asking_price",
        "offer_price", "owner_name", "owner_email", "owner_phone",
        "feasibility_score", "feasibility_json", "expected_close_date",
        "assigned_to_user_id", "status", "max_units_residential",
    ]
    for field in allowed_fields:
        if field in payload:
            setattr(deal, field, payload[field])
    await db.commit()
    await db.refresh(deal)
    return _deal_to_dict(deal)


@router.delete("/deals/{deal_id}")
async def soft_delete_deal(
    deal_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Soft delete a deal."""
    deal = await _get_deal_or_404(deal_id, db)
    deal.is_deleted = True
    deal.status = "archived"
    await db.commit()
    await db.refresh(deal)
    return {"message": "Deal soft deleted", "deal_id": deal_id}


# ---------------------------------------------------------------------------
# Pipeline transitions
# ---------------------------------------------------------------------------

@router.post("/deals/{deal_id}/transition")
async def transition_deal(
    deal_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_session),
):
    """Move a deal to a new pipeline stage."""
    deal = await _get_deal_or_404(deal_id, db)
    to_stage = payload.get("to_stage")
    user_id = payload.get("user_id", "")
    trigger_type = payload.get("trigger_type", "manual")

    if not to_stage:
        raise HTTPException(status_code=400, detail="Missing 'to_stage'")

    if deal.is_deleted:
        raise HTTPException(status_code=409, detail="Cannot transition a deleted deal")

    if deal.stage == to_stage:
        return {"message": "Deal already in target stage", "deal": _deal_to_dict(deal)}

    valid_next = VALID_TRANSITIONS.get(deal.stage, [])
    if to_stage not in valid_next:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {deal.stage} to {to_stage}. Valid: {valid_next}",
        )

    from_stage = deal.stage
    deal.stage = to_stage
    deal.stage_entered_at = datetime.datetime.now(datetime.timezone.utc)

    history = DealStageHistory(
        workspace_id=deal.workspace_id,
        deal_id=deal.id,
        from_stage=from_stage,
        to_stage=to_stage,
        transitioned_by_user_id=user_id,
        trigger_type=trigger_type,
    )
    db.add(history)
    await db.commit()
    await db.refresh(deal)
    return _deal_to_dict(deal)


@router.get("/deals/{deal_id}/history")
async def get_deal_history(
    deal_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Get stage transition history for a deal."""
    await _get_deal_or_404(deal_id, db)
    result = await db.execute(
        select(DealStageHistory)
        .where(DealStageHistory.deal_id == deal_id)
        .order_by(desc(DealStageHistory.transitioned_at))
    )
    history = result.scalars().all()
    return {"items": [_history_to_dict(h) for h in history]}


@router.get("/deals/stages")
async def get_pipeline_stages():
    """Return all pipeline stages and valid transitions."""
    return {
        "stages": PIPELINE_STAGES,
        "transitions": VALID_TRANSITIONS,
    }


@router.get("/deals/metrics")
async def get_pipeline_metrics(
    workspace_id: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    """Get aggregate pipeline metrics."""
    stmt = select(Deal).where(Deal.is_deleted == False)  # noqa: E712
    if workspace_id:
        stmt = stmt.where(Deal.workspace_id == workspace_id)
    result = await db.execute(stmt)
    deals = result.scalars().all()

    stage_counts: dict[str, int] = {s: 0 for s in PIPELINE_STAGES}
    total_value = 0.0
    for d in deals:
        stage_counts[d.stage] = stage_counts.get(d.stage, 0) + 1
        if d.asking_price:
            total_value += d.asking_price

    return {
        "total_deals": len(deals),
        "stage_distribution": stage_counts,
        "total_pipeline_value": total_value,
    }


# ---------------------------------------------------------------------------
# Outreach activities
# ---------------------------------------------------------------------------

@router.post("/deals/{deal_id}/outreach", status_code=201)
async def log_outreach(
    deal_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_session),
):
    """Log an outreach activity for a deal."""
    deal = await _get_deal_or_404(deal_id, db)
    activity_type = payload.get("activity_type")
    if not activity_type or activity_type not in ("email", "call", "meeting"):
        raise HTTPException(status_code=400, detail="Invalid activity_type (email|call|meeting)")

    activity = OutreachActivity(
        workspace_id=deal.workspace_id,
        deal_id=deal_id,
        activity_type=activity_type,
        direction=payload.get("direction", "outbound"),
        subject=payload.get("subject"),
        body=payload.get("body"),
        call_duration_seconds=payload.get("call_duration_seconds"),
        call_outcome=payload.get("call_outcome"),
        sentiment=payload.get("sentiment"),
        status="completed" if activity_type in ("call", "meeting") else payload.get("status", "draft"),
        to_address=payload.get("to_address"),
        to_name=payload.get("to_name"),
        from_address=payload.get("from_address"),
        from_name=payload.get("from_name"),
        created_by_user_id=payload.get("created_by_user_id"),
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    # Auto-create follow-up task for interested calls
    if activity_type == "call" and activity.call_outcome in ("interested", "follow_up"):
        # For now, return task recommendation in response
        pass

    return _outreach_to_dict(activity)


@router.get("/deals/{deal_id}/outreach")
async def list_outreach(
    deal_id: str,
    activity_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
):
    """List outreach activities for a deal."""
    await _get_deal_or_404(deal_id, db)
    stmt = (
        select(OutreachActivity)
        .where(OutreachActivity.deal_id == deal_id)
        .order_by(desc(OutreachActivity.created_at))
    )
    if activity_type:
        stmt = stmt.where(OutreachActivity.activity_type == activity_type)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    activities = result.scalars().all()
    return {"items": [_outreach_to_dict(a) for a in activities]}


@router.get("/outreach/metrics")
async def get_outreach_metrics(
    workspace_id: str | None = None,
    deal_id: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    """Get outreach activity metrics."""
    stmt = select(OutreachActivity)
    if deal_id:
        stmt = stmt.where(OutreachActivity.deal_id == deal_id)
    if workspace_id:
        stmt = stmt.where(OutreachActivity.workspace_id == workspace_id)
    result = await db.execute(stmt)
    activities = result.scalars().all()

    total = len(activities)
    emails = sum(1 for a in activities if a.activity_type == "email")
    calls = sum(1 for a in activities if a.activity_type == "call")
    meetings = sum(1 for a in activities if a.activity_type == "meeting")
    interested = sum(1 for a in activities if a.call_outcome == "interested")

    last_contact = None
    if activities:
        last = max(activities, key=lambda a: a.created_at or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
        last_contact = last.created_at.isoformat() if last.created_at else None

    return {
        "total_activities": total,
        "emails": emails,
        "calls": calls,
        "meetings": meetings,
        "interested_calls": interested,
        "last_contact": last_contact,
    }


# ---------------------------------------------------------------------------
# CRM Connectors
# ---------------------------------------------------------------------------

@router.get("/connectors")
async def list_connectors(
    workspace_id: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    """List connected CRM accounts."""
    if workspace_id:
        result = await db.execute(
            select(ConnectorAccount).where(ConnectorAccount.workspace_id == workspace_id)
        )
    else:
        result = await db.execute(select(ConnectorAccount))
    accounts = result.scalars().all()
    return {"items": [_connector_to_dict(a) for a in accounts]}


@router.post("/connectors", status_code=201)
async def create_connector(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_session),
):
    """Connect a new CRM account."""
    required = ["workspace_id", "provider", "auth_type"]
    for field in required:
        if not payload.get(field):
            raise HTTPException(status_code=400, detail=f"Missing: {field}")

    account = ConnectorAccount(
        workspace_id=payload["workspace_id"],
        provider=payload["provider"],
        auth_type=payload["auth_type"],
        scopes=payload.get("scopes", []),
        status="connected",
        encrypted_credentials_ref=payload.get("encrypted_credentials_ref"),
        metadata_json=payload.get("metadata_json", {}),
        created_by_user_id=payload.get("created_by_user_id"),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return _connector_to_dict(account)


@router.get("/connectors/{connector_id}")
async def get_connector(
    connector_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Get a connector by ID."""
    result = await db.execute(
        select(ConnectorAccount).where(ConnectorAccount.id == connector_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Connector not found")
    return _connector_to_dict(account)


@router.delete("/connectors/{connector_id}")
async def delete_connector(
    connector_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Disconnect a CRM account."""
    result = await db.execute(
        select(ConnectorAccount).where(ConnectorAccount.id == connector_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Connector not found")
    await db.delete(account)
    await db.commit()
    return {"message": "Connector disconnected", "connector_id": connector_id}


@router.post("/deals/{deal_id}/sync")
async def sync_deal_to_crm(
    deal_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_session),
):
    """Sync a deal to connected CRMs (placeholder for actual sync logic)."""
    deal = await _get_deal_or_404(deal_id, db)
    workspace_id = deal.workspace_id

    result = await db.execute(
        select(ConnectorAccount).where(
            ConnectorAccount.workspace_id == workspace_id,
            ConnectorAccount.status == "connected",
        )
    )
    accounts = result.scalars().all()

    sync_results = []
    for account in accounts:
        crm_id = f"{account.provider}_{deal.id}"
        deal.crm_sync_json[account.provider] = crm_id
        sync_results.append({
            "provider": account.provider,
            "success": True,
            "crm_object_id": crm_id,
        })

    await db.commit()
    return {
        "deal_id": deal_id,
        "synced_to": len(sync_results),
        "results": sync_results,
    }


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.post("/deals/{deal_id}/documents", status_code=201)
async def upload_document(
    deal_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    """Upload a document for a deal."""
    deal = await _get_deal_or_404(deal_id, db)
    filename = file.filename or "unnamed"

    # Reject malicious file types
    banned = (".exe", ".bat", ".sh", ".dll", ".cmd", ".scr")
    if filename.lower().endswith(banned):
        raise HTTPException(status_code=400, detail="Executable files not allowed")

    content = await file.read()
    doc = Document(
        workspace_id=deal.workspace_id,
        project_id=deal.project_id,
        site_id=deal.site_id,
        document_type="site_plan",
        status="pending",
        storage_url=f"/uploads/{filename}",
        metadata_json={"filename": filename, "size_bytes": len(content)},
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return {
        "id": doc.id,
        "filename": filename,
        "status": doc.status,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.get("/deals/{deal_id}/documents")
async def list_documents(
    deal_id: str,
    db: AsyncSession = Depends(get_session),
):
    """List documents for a deal."""
    deal = await _get_deal_or_404(deal_id, db)
    result = await db.execute(
        select(Document)
        .where(Document.project_id == deal.project_id)
        .order_by(desc(Document.created_at))
    )
    docs = result.scalars().all()
    return {
        "items": [
            {
                "id": d.id,
                "document_type": d.document_type,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }


@router.post("/documents/{doc_id}/analyze")
async def analyze_document(
    doc_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Trigger document OCR and analysis (mock)."""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = "completed"
    doc.metadata_json["ocr_status"] = "completed"
    doc.metadata_json["ocr_text"] = "Extracted text from document..."
    await db.commit()
    return {"id": doc_id, "status": doc.status, "insights": [{"type": "zoning_conflict", "severity": "high"}]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_deal_or_404(deal_id: str, db: AsyncSession) -> Deal:
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return deal


def _deal_to_dict(deal: Deal) -> dict[str, Any]:
    return {
        "id": deal.id,
        "workspace_id": deal.workspace_id,
        "project_id": deal.project_id,
        "site_id": deal.site_id,
        "title": deal.title,
        "description": deal.description,
        "deal_type": deal.deal_type,
        "property_address": deal.property_address,
        "owner_name": deal.owner_name,
        "owner_email": deal.owner_email,
        "owner_phone": deal.owner_phone,
        "asking_price": deal.asking_price,
        "offer_price": deal.offer_price,
        "feasibility_score": deal.feasibility_score,
        "stage": deal.stage,
        "status": deal.status,
        "is_deleted": deal.is_deleted,
        "assigned_to_user_id": deal.assigned_to_user_id,
        "source": deal.source,
        "stage_entered_at": deal.stage_entered_at.isoformat() if deal.stage_entered_at else None,
        "created_at": deal.created_at.isoformat() if deal.created_at else None,
        "updated_at": deal.updated_at.isoformat() if deal.updated_at else None,
    }


def _outreach_to_dict(activity: OutreachActivity) -> dict[str, Any]:
    return {
        "id": activity.id,
        "deal_id": activity.deal_id,
        "activity_type": activity.activity_type,
        "direction": activity.direction,
        "subject": activity.subject,
        "body": activity.body,
        "call_outcome": activity.call_outcome,
        "call_duration_seconds": activity.call_duration_seconds,
        "sentiment": activity.sentiment,
        "to_address": activity.to_address,
        "to_name": activity.to_name,
        "status": activity.status,
        "created_at": activity.created_at.isoformat() if activity.created_at else None,
    }


def _history_to_dict(history: DealStageHistory) -> dict[str, Any]:
    return {
        "id": history.id,
        "deal_id": history.deal_id,
        "from_stage": history.from_stage,
        "to_stage": history.to_stage,
        "transitioned_at": history.transitioned_at.isoformat() if history.transitioned_at else None,
        "transitioned_by_user_id": history.transitioned_by_user_id,
        "trigger_type": history.trigger_type,
    }


def _connector_to_dict(account: ConnectorAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "workspace_id": account.workspace_id,
        "provider": account.provider,
        "auth_type": account.auth_type,
        "scopes": account.scopes,
        "status": account.status,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }
