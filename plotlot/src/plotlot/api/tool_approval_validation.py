from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from plotlot.storage.db import get_session
from plotlot.storage.models import ApprovalRequest

logger = logging.getLogger(__name__)


async def validated_approved_ids(
    *,
    approval_ids: set[str],
    workspace_id: str,
) -> set[str]:
    if not approval_ids:
        return set()

    session = await get_session()
    try:
        now = datetime.now(timezone.utc)
        approved: set[str] = set()
        for approval_id in approval_ids:
            row = await session.get(ApprovalRequest, approval_id)
            if (
                row
                and row.workspace_id == workspace_id
                and row.status == "approved"
                and (row.expires_at is None or row.expires_at > now)
            ):
                approved.add(approval_id)
        return approved
    except SQLAlchemyError:
        logger.warning("Approval validation failed; failing closed", exc_info=True)
        return set()
    finally:
        await session.close()
