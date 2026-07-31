from contextvars import ContextVar, Token


_tenant_id: ContextVar[str | None] = ContextVar("plotlot_tenant_id", default=None)


def current_tenant_id() -> str | None:
    return _tenant_id.get()


def set_tenant(tenant_id: str) -> Token[str | None]:
    return _tenant_id.set(tenant_id)


def reset_tenant(token: Token[str | None]) -> None:
    _tenant_id.reset(token)
