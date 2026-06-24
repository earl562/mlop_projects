"""Unit tests for the AssumptionSet SQLAlchemy model."""

from __future__ import annotations

import pytest
from plotlot.storage.models import AssumptionSet


class FakeSession:
    def __init__(self):
        self._objects: dict[str, object] = {}

    def add(self, obj: object) -> None:
        name = obj.__class__.__name__
        if name == "AssumptionSet":
            self._objects[getattr(obj, "id")] = obj

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_create_assumption_set() -> None:
    """Create AssumptionSet with required fields, add to session, read back."""
    a = AssumptionSet(
        id="as_test_1",
        workspace_id="ws_1",
        analysis_id="an_1",
        created_by="user_test",
        version=1,
    )
    assert a.id == "as_test_1"
    assert a.workspace_id == "ws_1"
    assert a.analysis_id == "an_1"
    assert a.version == 1

    session = FakeSession()
    session.add(a)
    await session.commit()

    stored = session._objects["as_test_1"]
    assert stored is a
    assert getattr(stored, "id") == "as_test_1"
    assert getattr(stored, "analysis_id") == "an_1"
    assert getattr(stored, "version") == 1


@pytest.mark.asyncio
async def test_assumption_set_defaults() -> None:
    """Verify column-level defaults via metadata inspection."""
    cols = AssumptionSet.__table__.c

    assert cols.version.default.arg == 1
    assert cols.inputs_json.default.is_callable
    assert cols.labels_json.default.is_callable
    assert cols.supersedes_id.default is None
