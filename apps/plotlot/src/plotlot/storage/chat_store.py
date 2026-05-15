"""Durable chat persistence helpers.

Goal: make the backend the source of truth for agent chat sessions.

- Chat transcripts (user/assistant) are stored in `chat_messages`.
- Tool calls are stored in `chat_tool_calls` as an append-only audit trail.

All functions are best-effort: callers may catch and degrade to in-memory
behavior when the database is unavailable.
"""

from __future__ import annotations

from sqlalchemy import delete, select

from plotlot.storage.db import get_session
from plotlot.storage.models import ChatMessageRecord, ChatToolCallRecord

# Avoid storing unbounded payloads.
_MAX_MESSAGE_CHARS = 20_000
_MAX_TOOL_RESULT_CHARS = 40_000


def _truncate(text: str, limit: int) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[TRUNCATED]"


async def load_chat_messages(session_id: str, *, limit: int = 50) -> list[dict]:
    """Load the most recent transcript messages for a session.

    Returns a list of `{role, content}` dictionaries in chronological order.
    """

    session = await get_session()
    try:
        stmt = (
            select(ChatMessageRecord)
            .where(ChatMessageRecord.session_id == session_id)
            .order_by(ChatMessageRecord.id.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return [{"role": r.role, "content": r.content} for r in rows]
    finally:
        await session.close()


async def append_chat_message(session_id: str, role: str, content: str) -> None:
    """Append a transcript message."""

    session = await get_session()
    try:
        session.add(
            ChatMessageRecord(
                session_id=session_id,
                role=role,
                content=_truncate(content or "", _MAX_MESSAGE_CHARS),
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def load_tool_calls(session_id: str, *, limit: int = 200) -> list[dict]:
    """Load the most recent tool calls for a session.

    Returned in chronological order.
    """

    session = await get_session()
    try:
        stmt = (
            select(ChatToolCallRecord)
            .where(ChatToolCallRecord.session_id == session_id)
            .order_by(ChatToolCallRecord.id.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return [
            {
                "id": r.id,
                "tool_call_id": r.tool_call_id,
                "tool": r.tool_name,
                "args": r.tool_args,
                "result": r.tool_result,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        await session.close()


async def append_tool_call(
    session_id: str,
    *,
    tool_name: str,
    tool_args: dict,
    tool_result: str | None,
    tool_call_id: str | None = None,
    status: str = "complete",
) -> None:
    """Append a tool call audit record."""

    session = await get_session()
    try:
        session.add(
            ChatToolCallRecord(
                session_id=session_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_args=tool_args or {},
                tool_result=_truncate(tool_result or "", _MAX_TOOL_RESULT_CHARS)
                if tool_result
                else None,
                status=status,
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def delete_chat_session(session_id: str) -> None:
    """Delete all persisted data for a chat session."""

    session = await get_session()
    try:
        await session.execute(
            delete(ChatMessageRecord).where(ChatMessageRecord.session_id == session_id)
        )
        await session.execute(
            delete(ChatToolCallRecord).where(ChatToolCallRecord.session_id == session_id)
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
