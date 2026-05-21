"""Schema-shape tests for workspace/harness persistence tables.

These tests lock in the minimal durable spine:
workspace -> project -> site -> analysis -> run -> tool/evidence/approval.
"""

from plotlot.storage.models import (
    Analysis,
    AnalysisRun,
    ApprovalRequest,
    ConnectorAccount,
    ConnectorDataset,
    ConnectorSyncRun,
    Document,
    EvalCaseResult,
    EvalRun,
    EvidenceItem,
    GoldSetCase,
    ModelRun,
    Project,
    ProjectBranch,
    Report,
    Site,
    ToolRun,
    Workspace,
    WorkspaceMember,
)


def _column_names(model: type) -> set[str]:
    return {column.name for column in model.__table__.columns}


def test_workspace_models_define_tenant_spine() -> None:
    assert {"id", "name", "owner_user_id", "settings_json"}.issubset(_column_names(Workspace))
    assert {"workspace_id", "user_id", "role"}.issubset(_column_names(WorkspaceMember))


def test_project_site_models_define_primary_abstraction() -> None:
    assert {"workspace_id", "name", "status"}.issubset(_column_names(Project))
    assert {"workspace_id", "project_id", "address", "facts_json"}.issubset(_column_names(Site))
    assert "parent_branch_id" in _column_names(ProjectBranch)


def test_analysis_models_capture_skill_execution() -> None:
    assert {"workspace_id", "project_id", "skill_name", "status"}.issubset(_column_names(Analysis))
    assert {
        "workspace_id",
        "project_id",
        "analysis_id",
        "skill_name",
        "input_json",
        "output_json",
        "started_at",
        "completed_at",
    }.issubset(_column_names(AnalysisRun))


def test_tool_evidence_and_approval_models_support_governance() -> None:
    assert {"tool_name", "risk_class", "status", "input_json", "output_json"}.issubset(
        _column_names(ToolRun)
    )
    assert {
        "claim_key",
        "source_type",
        "source_url",
        "retrieval_method",
        "trust_label",
        "content_hash",
        "tool_name",
        "confidence",
        "retrieved_at",
    }.issubset(_column_names(EvidenceItem))
    assert {"workspace_id", "tool_run_id", "status", "risk_class", "action_name"}.issubset(
        _column_names(ApprovalRequest)
    )


def test_model_runs_capture_llm_audit_data() -> None:
    assert {
        "workspace_id",
        "provider",
        "model",
        "purpose",
        "input_tokens",
        "output_tokens",
    }.issubset(_column_names(ModelRun))


def test_report_document_connector_and_eval_models_exist() -> None:
    assert {"workspace_id", "report_json", "evidence_ids", "version"}.issubset(
        _column_names(Report)
    )
    assert {"workspace_id", "document_type", "status", "storage_url"}.issubset(
        _column_names(Document)
    )

    assert {"workspace_id", "provider", "auth_type", "scopes", "status"}.issubset(
        _column_names(ConnectorAccount)
    )
    assert {"provider", "topic", "endpoint_url", "official_status"}.issubset(
        _column_names(ConnectorDataset)
    )
    assert {"status", "counts_json", "error_message"}.issubset(_column_names(ConnectorSyncRun))

    assert {"suite", "case_id", "jurisdiction", "expected_json"}.issubset(
        _column_names(GoldSetCase)
    )
    assert {"suite", "status", "metrics_json"}.issubset(_column_names(EvalRun))
    assert {"status", "diffs_json", "trajectory_metrics_json"}.issubset(
        _column_names(EvalCaseResult)
    )
