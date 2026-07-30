from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

import plotlot.storage.db as db_mod


@pytest.mark.asyncio
async def test_ensure_engine_rebuilds_for_new_loop_without_cross_loop_dispose() -> None:
    original_engine = db_mod._engine
    original_factory = db_mod._session_factory
    original_loop_id = db_mod._engine_loop_id

    stale_engine = Mock()
    stale_engine.dispose = AsyncMock()
    replacement_engine = object()

    db_mod._engine = stale_engine
    db_mod._session_factory = object()
    db_mod._engine_loop_id = 101

    try:
        with (
            patch("plotlot.storage.db._current_loop_id", return_value=202),
            patch("plotlot.storage.db._get_engine", return_value=replacement_engine),
        ):
            engine = await db_mod._ensure_engine()

        assert engine is replacement_engine
        assert db_mod._engine is replacement_engine
        assert db_mod._engine_loop_id == 202
        assert db_mod._session_factory is None
        stale_engine.dispose.assert_not_awaited()
    finally:
        db_mod._engine = original_engine
        db_mod._session_factory = original_factory
        db_mod._engine_loop_id = original_loop_id
