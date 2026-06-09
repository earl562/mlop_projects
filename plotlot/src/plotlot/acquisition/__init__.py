from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from plotlot.storage.models import (
    ConnectorAccount,
    ConnectorSyncSettings,
    Deal,
    DealStageHistory,
    OutreachActivity,
)


def create_deal(
    db: Session,
    workspace_id: str,
    project_id: str,
    title: str,
    property_address: str,
    **kwargs: Any,
) -> Deal:
    deal = Deal(
        workspace_id=workspace_id,
        project_id=project_id,
        title=title,
        property_address=property_address,
        stage="lead",
        status="active",
        **kwargs,
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal


def transition_deal_stage(
    db: Session,
    deal: Deal,
    to_stage: str,
    user_id: str = "",
    trigger_type: str = "manual",
) -> bool:
    valid_transitions = {
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
    if to_stage not in valid_transitions.get(deal.stage, []):
        raise ValueError(f"Cannot transition from {deal.stage} to {to_stage}")

    history = DealStageHistory(
        workspace_id=deal.workspace_id,
        deal_id=deal.id,
        from_stage=deal.stage,
        to_stage=to_stage,
        transitioned_by_user_id=user_id,
        trigger_type=trigger_type,
    )
    deal.stage = to_stage
    deal.stage_entered_at = datetime.utcnow()
    db.add(history)
    db.commit()
    return True


def log_outreach_activity(
    db: Session,
    deal_id: str,
    workspace_id: str,
    activity_type: str,
    **kwargs: Any,
) -> OutreachActivity:
    activity = OutreachActivity(
        deal_id=deal_id,
        workspace_id=workspace_id,
        activity_type=activity_type,
        status="sent" if activity_type == "email" else "completed",
        **kwargs,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def encrypt_credentials(raw: str) -> str:
    return raw[::-1] + "_encrypted"


def decrypt_credentials(encrypted: str) -> str:
    return encrypted[:-10][::-1]
