from __future__ import annotations

import pytest

from plotlot.harness.agents.models import AgentTask, WorkflowIntent
from plotlot.harness.agents.registry import (
    AgentToolViolationError,
    build_default_agent_registry,
)


def test_default_registry_exposes_specialists_for_all_workflows():
    registry = build_default_agent_registry()

    assert {spec.name for spec in registry.for_workflow(WorkflowIntent.SITE_FEASIBILITY)} == {
        "site_identity",
        "zoning_research",
        "feasibility",
        "reporting",
    }
    assert {spec.name for spec in registry.for_workflow(WorkflowIntent.LEAD_SOURCING)} == {
        "sourcing",
        "reporting",
    }
    assert {spec.name for spec in registry.for_workflow(WorkflowIntent.DEEP_UNDERWRITING)} == {
        "site_identity",
        "zoning_research",
        "feasibility",
        "underwriting",
        "reporting",
    }


def test_registry_rejects_cross_agent_tool_escalation():
    registry = build_default_agent_registry()
    task = AgentTask(
        task_id="identity.send",
        agent_name="site_identity",
        tool_name="gmail_send_draft",
    )

    with pytest.raises(AgentToolViolationError, match="site_identity"):
        registry.validate_task(task)


def test_registry_accepts_declared_tool():
    registry = build_default_agent_registry()
    task = AgentTask(
        task_id="feasibility.analyze",
        agent_name="feasibility",
        tool_name="analyze_property",
        arguments={"address": "123 Main St"},
    )

    registry.validate_task(task)
