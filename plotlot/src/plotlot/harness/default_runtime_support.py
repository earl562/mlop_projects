from __future__ import annotations

import uuid

from plotlot.land_use.models import ToolContext


def ev_id() -> str:
    return str(uuid.uuid4())


def default_project_id(workspace_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"plotlot:{workspace_id}:default_project"))


def project_id(context: ToolContext) -> str:
    return context.project_id or default_project_id(context.workspace_id)
