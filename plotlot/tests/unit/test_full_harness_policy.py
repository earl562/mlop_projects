from __future__ import annotations

from plotlot.domain.types import ToolContext
from plotlot.harness.full_harness_registry import get_tool_spec
from plotlot.harness.policy import HarnessPolicyEngine, HarnessPolicyRequest


def _context(*, approved_approval_ids: set[str] | None = None) -> ToolContext:
    return ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_fixture_policy",
        live_network_allowed=False,
        approved_approval_ids=approved_approval_ids or set(),
    )


def test_harness_policy_allows_allowlisted_tool_specs() -> None:
    decision = HarnessPolicyEngine().authorize_tool_spec(
        HarnessPolicyRequest(
            tool_spec=get_tool_spec("search_municode"),
            context=_context(),
        )
    )

    assert decision.allowed is True
    assert decision.approval_required is False


def test_harness_policy_requires_approval_for_ask_tool_specs() -> None:
    engine = HarnessPolicyEngine()
    tool_spec = get_tool_spec("export_report")

    blocked = engine.authorize_tool_spec(
        HarnessPolicyRequest(tool_spec=tool_spec, context=_context())
    )
    approved = engine.authorize_tool_spec(
        HarnessPolicyRequest(
            tool_spec=tool_spec,
            context=_context(approved_approval_ids={"apr_run_fixture_policy_export_report"}),
        )
    )

    assert blocked.allowed is False
    assert blocked.approval_required is True
    assert blocked.approval_id == "apr_run_fixture_policy_export_report"
    assert approved.allowed is True
    assert approved.approval_required is False


def test_harness_policy_denies_blocked_tool_specs_even_with_approval() -> None:
    decision = HarnessPolicyEngine().authorize_tool_spec(
        HarnessPolicyRequest(
            tool_spec=get_tool_spec("download_protected_media"),
            context=_context(
                approved_approval_ids={"apr_run_fixture_policy_download_protected_media"}
            ),
        )
    )

    assert decision.allowed is False
    assert decision.approval_required is False
    assert "denied" in decision.reason
