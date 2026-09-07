"""SQLAlchemy ORM models for pgvector storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from plotlot.domain.dimensional_standard import DistrictDimensionalStandard, VerificationStatus
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from plotlot.storage.model_base import Base
from plotlot.storage.tenant_models import (
    ConnectorCredential as ConnectorCredential,
)
from plotlot.storage.tenant_models import PortfolioEntry as PortfolioEntry
from plotlot.storage.tenant_models import ReportCache as ReportCache


def _uuid() -> str:
    """Return a string UUID for durable workspace-native records."""

    return str(uuid4())


class OrdinanceChunk(Base):
    """A chunk of zoning ordinance text with its embedding vector."""

    __tablename__ = "ordinance_chunks"
    __table_args__ = (
        UniqueConstraint(
            "municipality",
            "municode_node_id",
            "chunk_index",
            name="uq_chunk_natural_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    municipality: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    county: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    chapter: Mapped[str | None] = mapped_column(String(500))
    section: Mapped[str | None] = mapped_column(String(200))
    section_title: Mapped[str | None] = mapped_column(String(500))
    zone_codes: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=[])
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[Any | None] = mapped_column(Vector(1024))
    municode_node_id: Mapped[str | None] = mapped_column(String(200))
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR)

    # Lineage fields (B2) — provenance tracking for each chunk
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)

    # State/region field (B6) — supports multi-state expansion (FL, NC, etc.)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True, default="FL")

    # Phase 1 master-spec §7 columns (migration 010) — source authority + snapshot linkage.
    source_authority_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    chunk_kind: Mapped[str | None] = mapped_column(String(40), nullable=True, default="narrative")
    quality_flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    table_row_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrdinanceSection(Base):
    """One row per ordinance section: the hierarchical index over chunks.

    While `OrdinanceChunk` is the embedding/retrieval unit, `OrdinanceSection`
    is the *structural* unit: a section's path (breadcrumb), its role
    (`section_type`), and its outbound cross-references (`cross_refs`). This
    is the substrate for Phase 8's AgenticRAG — `open_section` / `follow_cross_ref`
    tools navigate this index, and the `dimensional_table` fast-path (Slice 8.2)
    selects rows by `section_type='dimensional_table'`. `referenced_by` is the
    reverse index (node_ids that cite this section); it defaults to empty and is
    populated by the Slice 3.5 backfill that scans every section's `cross_refs`.

    Natural key: (municipality, node_id) — one section per municode node, even
    though a section fans out to many chunks. `state` is nullable so PDF-only
    municipalities (San Diego) that lack a municode node_id can still index
    sections once their scraper supplies a synthetic node_id (Slice 3.5).
    """

    __tablename__ = "ordinance_sections"
    __table_args__ = (
        UniqueConstraint(
            "municipality",
            "node_id",
            name="uq_section_natural_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    municipality: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    county: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True, default="FL")
    # municode node id; synthetic for PDF-only sources. Null only before first
    # backfill — the natural-key constraint treats (municipality, node_id), so a
    # null node_id still enforces one row per municipality-null group.
    node_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    heading: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    section_number: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    section_title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # regulation | definition | schedule | dimensional_table | use_regulation
    section_type: Mapped[str] = mapped_column(String(40), nullable=False, default="regulation")

    # Hierarchical breadcrumb, root-first: ["Chapter 47", "Sec. 47-5.60"].
    path: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=[])
    # Outbound section-number references extracted from the section text
    # (e.g. ["47-24.3", "47-5.601"]). Drives follow_cross_ref traversal.
    cross_refs: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=[])
    # Reverse index: node_ids whose cross_refs cite this section. Populated by
    # the Slice 3.5 backfill; empty until then.
    referenced_by: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=[])

    # Provenance — mirrors OrdinanceChunk lineage so freshness (Slice 3.4) and
    # source-boundary checks can resolve against the section, not just chunks.
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 1 master-spec §7 columns (migration 010)
    source_authority_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quality_flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class IngestionCheckpoint(Base):
    """Tracks per-municipality ingestion progress for resumable batch jobs.

    DDIA pattern: idempotent writes with checkpointing. Each municipality
    is a partition — failures are isolated, progress is persistent, and
    the pipeline resumes from where it left off.
    """

    __tablename__ = "ingestion_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    municipality_key: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending|running|complete|failed
    chunks_stored: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("batch_id", "municipality_key", name="uq_checkpoint_batch_muni"),
    )


class UserSubscription(Base):
    """Tracks each user's plan tier and monthly analysis usage.

    Created on first authenticated request.  ``analyses_used`` resets monthly
    via Stripe ``invoice.paid`` webhook or when ``period_end`` has passed.
    """

    __tablename__ = "user_subscriptions"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    plan: Mapped[str] = mapped_column(String, default="free", nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    analyses_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Workspace(Base):
    """Top-level tenant and collaboration boundary."""

    __tablename__ = "workspaces"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    slug = Column(String(120), nullable=True, unique=True)
    owner_user_id = Column(String, nullable=True, index=True)
    settings_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkspaceMember(Base):
    """User membership inside a workspace."""

    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member_user"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    clerk_organization_id = Column(String(120), nullable=True, index=True)
    role = Column(String(50), nullable=False, default="viewer")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ServicePrincipal(Base):
    """Tenant-scoped non-human identity with an explicitly bounded action set."""

    __tablename__ = "service_principals"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    allowed_actions: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Project(Base):
    """A land-use or site-feasibility initiative inside a workspace."""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(40), nullable=False, default="active", index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProjectBranch(Base):
    """Scenario fork for project-level iteration."""

    __tablename__ = "project_branches"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_branch_name"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    parent_branch_id = Column(String(36), ForeignKey("project_branches.id"), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Site(Base):
    """A parcel, assemblage, or candidate location."""

    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("project_id", "parcel_id", name="uq_site_project_parcel"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    address = Column(String(300), nullable=False, index=True)
    parcel_id = Column(String(120), nullable=True, index=True)
    geometry_json = Column(JSON, nullable=False, default=dict)
    facts_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Analysis(Base):
    """Durable analysis definition for a project or site."""

    __tablename__ = "analyses"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    site_id = Column(String(36), ForeignKey("sites.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    skill_name = Column(String(120), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="active", index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AnalysisRun(Base):
    """One execution of a harness skill or workflow."""

    __tablename__ = "analysis_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    site_id = Column(String(36), ForeignKey("sites.id"), nullable=True, index=True)
    analysis_id = Column(String(36), ForeignKey("analyses.id"), nullable=True, index=True)
    skill_name = Column(String(120), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="pending", index=True)
    input_json = Column(JSON, nullable=False, default=dict)
    output_json = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EvidenceItem(Base):
    """A source-backed claim recorded by the harness runtime."""

    __tablename__ = "evidence_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    site_id = Column(String(36), ForeignKey("sites.id"), nullable=True, index=True)
    analysis_id = Column(String(36), ForeignKey("analyses.id"), nullable=True, index=True)
    analysis_run_id = Column(String(36), ForeignKey("analysis_runs.id"), nullable=True, index=True)
    tool_run_id = Column(String(36), ForeignKey("tool_runs.id"), nullable=True, index=True)
    claim_key = Column(String(200), nullable=False, index=True)
    value_json = Column(JSON, nullable=False, default=dict)
    source_type = Column(String(80), nullable=False, index=True)
    source_url = Column(String, nullable=True)
    source_title = Column(String(500), nullable=True)
    source_excerpt = Column(Text, nullable=True)
    retrieval_method = Column(String(80), nullable=False, default="connector_result", index=True)
    trust_label = Column(String(40), nullable=False, default="medium", index=True)
    source_version = Column(String(200), nullable=True)
    content_hash = Column(String(128), nullable=True, index=True)
    tool_name = Column(String(120), nullable=False, index=True)
    confidence = Column(String(40), nullable=False, default="medium", index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ToolRun(Base):
    """Audit record for a deterministic tool invocation."""

    __tablename__ = "tool_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    site_id = Column(String(36), ForeignKey("sites.id"), nullable=True, index=True)
    analysis_id = Column(String(36), ForeignKey("analyses.id"), nullable=True, index=True)
    analysis_run_id = Column(String(36), ForeignKey("analysis_runs.id"), nullable=True, index=True)
    tool_name = Column(String(120), nullable=False, index=True)
    risk_class = Column(String(40), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="pending", index=True)
    input_json = Column(JSON, nullable=False, default=dict)
    output_json = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ModelRun(Base):
    """Audit record for a model invocation."""

    __tablename__ = "model_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    analysis_run_id = Column(String(36), ForeignKey("analysis_runs.id"), nullable=True, index=True)
    provider = Column(String(80), nullable=False, index=True)
    model = Column(String(160), nullable=False, index=True)
    purpose = Column(String(160), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    reasoning_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApprovalRequest(Base):
    """Human approval gate for risky runtime actions."""

    __tablename__ = "approval_requests"

    # Approval IDs are also used as user-facing keys; allow longer deterministic IDs.
    id = Column(String(120), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    analysis_run_id = Column(String(36), ForeignKey("analysis_runs.id"), nullable=True, index=True)
    tool_run_id = Column(String(36), ForeignKey("tool_runs.id"), nullable=True, index=True)
    status = Column(String(40), nullable=False, default="pending", index=True)
    risk_class = Column(String(40), nullable=False, index=True)
    action_name = Column(String(160), nullable=False)
    reason = Column(Text, nullable=False)
    request_json = Column(JSON, nullable=False, default=dict)
    response_json = Column(JSON, nullable=False, default=dict)
    requested_by = Column(String, nullable=True, index=True)
    decided_by = Column(String, nullable=True, index=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Report(Base):
    """Durable report artifact generated from recorded evidence."""

    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    site_id = Column(String(36), ForeignKey("sites.id"), nullable=True, index=True)
    analysis_run_id = Column(String(36), ForeignKey("analysis_runs.id"), nullable=True, index=True)
    status = Column(String(40), nullable=False, default="draft", index=True)
    report_json = Column(JSON, nullable=False, default=dict)
    evidence_ids: Any = Column(ARRAY(String), nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Document(Base):
    """Exportable document artifact derived from a report."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    site_id = Column(String(36), ForeignKey("sites.id"), nullable=True, index=True)
    report_id = Column(String(36), ForeignKey("reports.id"), nullable=True, index=True)
    document_type = Column(String(80), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="draft", index=True)
    storage_url = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConnectorAccount(Base):
    """Workspace-scoped account for OAuth/API-key backed connectors."""

    __tablename__ = "connector_accounts"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    provider = Column(String(80), nullable=False, index=True)
    auth_type = Column(String(40), nullable=False)
    scopes: Any = Column(ARRAY(String), nullable=False, default=list)
    status = Column(String(40), nullable=False, default="connected", index=True)
    encrypted_credentials_ref = Column(String, nullable=True)
    created_by_user_id = Column(String, nullable=True, index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConnectorDataset(Base):
    """Discovered public or workspace connector dataset."""

    __tablename__ = "connector_datasets"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=True, index=True)
    provider = Column(String(80), nullable=False, index=True)
    jurisdiction = Column(String(200), nullable=True, index=True)
    topic = Column(String(120), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    endpoint_url = Column(String, nullable=False)
    metadata_url = Column(String, nullable=True)
    license_url = Column(String, nullable=True)
    official_status = Column(String(40), nullable=False, default="unknown", index=True)
    freshness_json = Column(JSON, nullable=False, default=dict)
    schema_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConnectorSyncRun(Base):
    """Audit record for connector dataset sync/discovery jobs."""

    __tablename__ = "connector_sync_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=True, index=True)
    connector_account_id = Column(
        String(36), ForeignKey("connector_accounts.id"), nullable=True, index=True
    )
    connector_dataset_id = Column(
        String(36), ForeignKey("connector_datasets.id"), nullable=True, index=True
    )
    status = Column(String(40), nullable=False, default="pending", index=True)
    counts_json = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GoldSetCase(Base):
    """Durable eval/golden case for zoning and site-feasibility workflows."""

    __tablename__ = "gold_set_cases"

    id = Column(String(36), primary_key=True, default=_uuid)
    suite = Column(String(120), nullable=False, index=True)
    case_id = Column(String(160), nullable=False, unique=True)
    jurisdiction = Column(String(200), nullable=False, index=True)
    address = Column(String(300), nullable=True)
    expected_json = Column(JSON, nullable=False, default=dict)
    source_urls: Any = Column(ARRAY(String), nullable=False, default=list)
    tags: Any = Column(ARRAY(String), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EvalRun(Base):
    """One eval run against a gold-set suite."""

    __tablename__ = "eval_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    suite = Column(String(120), nullable=False, index=True)
    git_sha = Column(String(80), nullable=True, index=True)
    model_profile = Column(String(160), nullable=True)
    status = Column(String(40), nullable=False, default="pending", index=True)
    metrics_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class EvalCaseResult(Base):
    """Per-case result for trajectory-aware eval scoring."""

    __tablename__ = "eval_case_results"

    id = Column(String(36), primary_key=True, default=_uuid)
    eval_run_id = Column(String(36), ForeignKey("eval_runs.id"), nullable=False, index=True)
    gold_set_case_id = Column(
        String(36), ForeignKey("gold_set_cases.id"), nullable=False, index=True
    )
    status = Column(String(40), nullable=False, index=True)
    diffs_json = Column(JSON, nullable=False, default=dict)
    evidence_metrics_json = Column(JSON, nullable=False, default=dict)
    trajectory_metrics_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DistrictDimensionalStandardORM(Base):
    """Typed, provenance-backed dimensional standards per zoning district.

    The verified-fact source for the calculator at query time (WIRE-1.1b): a
    district's setbacks / height / FAR / coverage / density come from a typed
    row extracted from the ordinance's Schedule of District Regulations at
    ingestion time, not from LLM re-parsing the table on every analysis.

    Provisioned by versioned Alembic migrations; populated by the ingestion
    extractor (Slice 3.2 generalizes across municipalities). Natural
    key: ``(municipality, district_code)`` — one row per (municipality, district).
    """

    __tablename__ = "district_dimensional_standards"
    __table_args__ = (
        UniqueConstraint(
            "municipality",
            "district_code",
            name="uq_district_dimensional_standard",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    municipality: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    county: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True, default="FL")
    district_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    min_lot_area_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_lot_width_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    setback_front_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    setback_side_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    setback_rear_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_height_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_lot_coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    far: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_density_units_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Provenance: the originating ordinance section (Slice 3.2's evidence graph).
    source_section_id: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_url: Mapped[str] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=func.now()
    )

    # Verification status (Slice 3.2 review): only VERIFIED rows produce
    # verified_fact/local_authority claims. STAGED rows are assumption-grade.
    verification_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="unverified", index=True
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def to_domain(self) -> DistrictDimensionalStandard:
        """Convert the ORM row to the frozen domain type the calculator consumes."""
        return DistrictDimensionalStandard(
            municipality=self.municipality,
            county=self.county,
            state=self.state or "",
            district_code=self.district_code,
            min_lot_area_sqft=self.min_lot_area_sqft,
            min_lot_width_ft=self.min_lot_width_ft,
            setback_front_ft=self.setback_front_ft,
            setback_side_ft=self.setback_side_ft,
            setback_rear_ft=self.setback_rear_ft,
            max_height_ft=self.max_height_ft,
            max_lot_coverage_pct=self.max_lot_coverage_pct,
            far=self.far,
            max_density_units_per_acre=self.max_density_units_per_acre,
            source_section_id=self.source_section_id,
            source_url=self.source_url or "",
            extracted_at=self.extracted_at or datetime.now(UTC),
            verification_status=VerificationStatus(self.verification_status or "unverified"),
        )


class CountySchema(Base):
    """Discovered ArcGIS dataset schemas and field mappings for any US county.

    Single source of truth for dynamic county property/zoning lookup.
    Replaces Firestore cache — county_key is the primary key (e.g. "san diego").
    TTL enforced in application code (default 7 days / 168 hours).
    """

    __tablename__ = "county_schemas"

    county_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    state: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    # Serialised DatasetInfo objects (nullable — may not have zoning layer)
    parcels_dataset: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    zoning_dataset: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Serialised FieldMapping (nullable — generated on first lookup)
    field_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    ttl_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=168)
    last_verified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# ---------------------------------------------------------------------------
# Phase 1 — master spec §7: source authorities, snapshots, harness events
# ---------------------------------------------------------------------------


class JurisdictionSourceAuthorityORM(Base):
    """A typed, provenance-backed source authority for one jurisdiction.

    Master spec §5 + §7. The ingestion unit — not "a city" but a
    (jurisdiction, scope, provider) triple. Natural key:
    (state, county, municipality, authority_scope, provider).
    """

    __tablename__ = "jurisdiction_source_authorities"
    __table_args__ = (
        UniqueConstraint(
            "state",
            "county",
            "municipality",
            "authority_scope",
            "provider",
            name="uq_jurisdiction_source_authority_natural_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    state: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    county: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    municipality: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    jurisdiction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    authority_scope: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(String(500), nullable=False)
    official_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    legal_caveat: Mapped[str] = mapped_column(Text, nullable=False)
    freshness_policy: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    supplement_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ingestion_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    coverage_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrdinanceSourceSnapshotORM(Base):
    """One raw fetch of a source authority's content (master spec §7).

    Stored BEFORE parsing (raw snapshot), content-hashed for idempotency.
    Natural key: (source_authority_id, content_hash).
    """

    __tablename__ = "ordinance_source_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source_authority_id",
            "content_hash",
            name="uq_ordinance_source_snapshot_natural_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    source_authority_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("jurisdiction_source_authorities.id"), nullable=False, index=True
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    etag: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class HarnessEventORM(Base):
    """Stable event envelope for ingestion + analysis runs (master spec §6).

    Persisted audit trail. Queryable by run (analysis_run_id / ingestion_run_id).
    Append-only.
    """

    __tablename__ = "harness_events"
    __table_args__ = (UniqueConstraint("id", name="uq_harness_event_id"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="info")
    workspace_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    site_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    analysis_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    analysis_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ingestion_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source_authority_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    tool_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
