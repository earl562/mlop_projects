from sqlalchemy import select

from plotlot.api.auth_types import (
    Actor,
    IdentityRole,
    capabilities_for_role,
)
from plotlot.storage.db import get_session
from plotlot.storage.models import WorkspaceMember


async def resolve_actor_membership(actor: Actor) -> Actor | None:
    if actor.tenant_id is None:
        return None

    session = await get_session()
    try:
        role_value = await session.scalar(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == actor.tenant_id,
                WorkspaceMember.user_id == actor.user_id,
            )
        )
    finally:
        await session.close()

    if role_value is None:
        return None
    role_text = str(role_value)
    if role_text == "member":
        role_text = IdentityRole.VIEWER.value
    try:
        role = IdentityRole(role_text)
    except ValueError:
        return None
    return Actor(
        user_id=actor.user_id,
        tenant_id=actor.tenant_id,
        role=role,
        capabilities=capabilities_for_role(role),
        email=actor.email,
    )
