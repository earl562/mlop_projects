from __future__ import annotations

from plotlot.harness.contracts import ExecutionMode, SourceMode
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_fixture_deal_analysis
from plotlot.harness.run_store import (
    HarnessRunCancellationRequest,
    RunCancellationBlockedError,
    LocalHarnessRunStore,
)
from plotlot.harness.tool_router import HarnessToolCallRequest, default_tool_router
from plotlot.domain.types import ToolContext


def test_local_store_persists_fixture_run_events(tmp_path) -> None:
    store_path = tmp_path / "runs.json"
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
            execution_mode=ExecutionMode.CLI,
        )
    )

    LocalHarnessRunStore(store_path).save_run(result)
    loaded = LocalHarnessRunStore(store_path).get_run(result.run_id)

    assert loaded.run_id == result.run_id
    assert [event.sequence for event in loaded.events] == list(range(1, len(loaded.events) + 1))
    assert loaded.events[0].type.value == "run.created"
    assert loaded.events[0].source.value == "cli"


def test_local_store_replay_returns_ordered_timeline(tmp_path) -> None:
    store = LocalHarnessRunStore(tmp_path / "runs.json")
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example Broward fixture address",
            analysis_type="zoning_research",
            source_mode=SourceMode.FIXTURE,
        )
    )

    store.save_run(result)
    replay = store.replay_run(result.run_id)

    assert replay.run_id == result.run_id
    assert replay.status == "completed"
    assert replay.event_count == len(result.events)
    assert replay.timeline[0].type == "run.created"
    assert replay.timeline[-1].type == "run.completed"


def test_local_store_appends_tool_events_with_run_sequence(tmp_path) -> None:
    store = LocalHarnessRunStore(tmp_path / "runs.json")
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example append events fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        )
    )
    tool_result = default_tool_router().call(
        HarnessToolCallRequest(
            tool_name="search_municode",
            args={"jurisdiction": "miami", "query": "parking"},
            context=ToolContext(
                workspace_id="ws_fixture",
                actor_user_id="analyst_fixture",
                run_id=str(result.run_id),
            ),
            source_mode=SourceMode.FIXTURE,
            execution_mode=ExecutionMode.CLI,
        )
    )

    store.save_run(result)
    appended = store.append_events(result.run_id, tool_result.events)
    replay = store.replay_run(result.run_id)

    assert [event.sequence for event in appended] == list(
        range(len(result.events) + 1, len(result.events) + len(appended) + 1)
    )
    assert replay.event_count == len(result.events) + len(appended)
    assert replay.timeline[-1].type == "tool.completed"


def test_local_store_cancels_queued_run_with_ordered_event(tmp_path) -> None:
    store = LocalHarnessRunStore(tmp_path / "runs.json")
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example cancellable queued fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        )
    ).model_copy(update={"status": "queued"})

    store.save_run(result)
    cancelled = store.cancel_run(
        HarnessRunCancellationRequest(
            run_id=result.run_id,
            actor_user_id="analyst_fixture",
            reason="No longer pursuing this site.",
            execution_mode=ExecutionMode.CLI,
        )
    )

    assert cancelled.status == "cancelled"
    assert [event.sequence for event in cancelled.events] == list(
        range(1, len(cancelled.events) + 1)
    )
    assert cancelled.events[-1].type == "run.cancelled"
    assert cancelled.events[-1].payload["actor_user_id"] == "analyst_fixture"
    assert store.replay_run(result.run_id).timeline[-1].type == "run.cancelled"


def test_local_store_rejects_completed_run_cancellation(tmp_path) -> None:
    store = LocalHarnessRunStore(tmp_path / "runs.json")
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example completed cancellation fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        )
    )

    store.save_run(result)

    try:
        store.cancel_run(
            HarnessRunCancellationRequest(
                run_id=result.run_id,
                actor_user_id="analyst_fixture",
                reason="Cancel after completion.",
                execution_mode=ExecutionMode.CLI,
            )
        )
    except RunCancellationBlockedError as exc:
        assert exc.run_id == result.run_id
        assert exc.current_status == "completed"
        events = store.get_events(result.run_id)
        assert events[-1].type == "run.cancelled"
        assert events[-1].status == "failed"
        assert events[-1].error is not None
        assert events[-1].error.code == "invalid_run_transition"
    else:
        raise AssertionError("completed runs must not be cancellable")


def test_local_store_treats_empty_existing_file_as_empty_snapshot(tmp_path) -> None:
    store_path = tmp_path / "runs.json"
    store_path.write_text("", encoding="utf-8")
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example empty store fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        )
    )

    LocalHarnessRunStore(store_path).save_run(result)

    assert LocalHarnessRunStore(store_path).get_run(result.run_id).run_id == result.run_id
