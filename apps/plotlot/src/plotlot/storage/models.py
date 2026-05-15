"""SQLAlchemy ORM models for pgvector storage."""

from pgvector.sqlalchemy import Vector
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
from sqlalchemy.dialects.postgresql import ARRAY, JSON, TSVECTOR
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


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

    id = Column(Integer, primary_key=True, autoincrement=True)
    municipality = Column(String(200), nullable=False, index=True)
    county = Column(String(100), nullable=False, index=True)
    chapter = Column(String(500))
    section = Column(String(200))
    section_title = Column(String(500))
    zone_codes: Column = Column(ARRAY(String), default=[])
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    embedding = Column(Vector(1024))
    municode_node_id = Column(String(200))
    search_vector = Column(TSVECTOR)

    # Lineage fields (B2) — provenance tracking for each chunk
    source_url = Column(String, nullable=True)  # Municode URL where this was scraped
    scraped_at = Column(DateTime(timezone=True), nullable=True)  # When it was scraped
    embedding_model = Column(String, nullable=True)  # e.g. "nvidia/nv-embedqa-e5-v5"

    # State/region field (B6) — supports multi-state expansion (FL, NC, etc.)
    state = Column(String(2), nullable=True, default="FL")  # Two-letter state code

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(50), nullable=False, index=True)
    municipality_key = Column(String(100), nullable=False)
    state = Column(String(2), nullable=False)
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending|running|complete|failed
    chunks_stored = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("batch_id", "municipality_key", name="uq_checkpoint_batch_muni"),
    )


class PortfolioEntry(Base):
    """A saved zoning analysis in the user's portfolio.

    Persists portfolio data across server restarts. The user_id column is
    nullable until auth (Supabase) is wired in — enables per-user filtering
    once authentication is enabled.
    """

    __tablename__ = "portfolio_entries"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=True, index=True)  # nullable until auth is wired in
    address = Column(String, nullable=False)
    municipality = Column(String, nullable=False)
    county = Column(String, nullable=False)
    zoning_district = Column(String, nullable=True)
    report_json = Column(JSON, nullable=False)  # full ZoningReportResponse as dict
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReportCache(Base):
    """Cached zoning report to avoid redundant LLM calls for repeated addresses.

    Reports are stored as JSON with a TTL (default 24h). The address_normalized
    column provides a unique, deterministic cache key derived from the raw address.
    """

    __tablename__ = "report_cache"

    id = Column(Integer, primary_key=True)
    address = Column(String, nullable=False, index=True)
    address_normalized = Column(String, nullable=False, unique=True)  # lowercase, stripped
    report_json = Column(JSON, nullable=False)  # full ZoningReportResponse as dict
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)  # TTL
    hit_count = Column(Integer, default=0)


class UserSubscription(Base):
    """Tracks each user's plan tier and monthly analysis usage.

    Created on first authenticated request.  ``analyses_used`` resets monthly
    via Stripe ``invoice.paid`` webhook or when ``period_end`` has passed.
    """

    __tablename__ = "user_subscriptions"

    user_id = Column(String, primary_key=True)  # Clerk user ID (sub claim)
    plan = Column(String, default="free", nullable=False)  # "free" | "pro"
    stripe_customer_id = Column(String, nullable=True, unique=True)
    stripe_subscription_id = Column(String, nullable=True)
    analyses_used = Column(Integer, default=0, nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Workspace(Base):
    """Top-level tenant/collaboration boundary for the PlotLot harness."""

    __tablename__ = "workspaces"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorkspaceMember(Base):
    """Workspace membership and role assignment."""

    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member_user"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    role = Column(String(32), nullable=False, default="owner")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    """A land-use or site-feasibility initiative."""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    project_type = Column(String(64), nullable=False, default="zoning_research")
    status = Column(String(32), nullable=False, default="active")
    criteria_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Site(Base):
    """Candidate parcel, assemblage, or location within a project."""

    __tablename__ = "sites"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    parcel_id = Column(String(128), nullable=True, index=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    score = Column(Float, nullable=True)
    site_type = Column(String(64), nullable=False, default="candidate")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AnalysisRun(Base):
    """A run of a skill/workflow against a project or site."""

    __tablename__ = "analysis_runs"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    site_id = Column(String(36), ForeignKey("sites.id"), nullable=True, index=True)
    skill_name = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, default="running")
    input_json = Column(JSON, nullable=False, default=dict)
    output_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class EvidenceItem(Base):
    """Claim-level provenance record used by reports and analyses."""

    __tablename__ = "evidence_items"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    site_id = Column(String(36), ForeignKey("sites.id"), nullable=True, index=True)
    analysis_run_id = Column(String(36), ForeignKey("analysis_runs.id"), nullable=True, index=True)
    claim_key = Column(String(128), nullable=False, index=True)
    value_json = Column(JSON, nullable=False, default=dict)
    source_type = Column(String(64), nullable=False)
    source_url = Column(Text, nullable=True)
    source_title = Column(Text, nullable=True)
    tool_name = Column(String(128), nullable=False)
    confidence = Column(String(16), nullable=False, default="medium")
    retrieved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    """Generated report artifact metadata."""

    __tablename__ = "reports"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    site_id = Column(String(36), ForeignKey("sites.id"), nullable=True, index=True)
    report_type = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    content_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApprovalRequest(Base):
    """Human approval request for risky tool execution."""

    __tablename__ = "approval_requests"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=True, index=True)
    tool_name = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    reason = Column(Text, nullable=False, default="")
    request_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class ChatMessageRecord(Base):
    """Durable chat transcript message (user/assistant).

    PlotLot's chat endpoint historically relied on in-memory session state.
    This table provides durable, backend-owned transcript persistence.
    """

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(32), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # user|assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChatToolCallRecord(Base):
    """Append-only audit log of tool calls made during chat runs."""

    __tablename__ = "chat_tool_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(32), nullable=False, index=True)
    tool_call_id = Column(String(64), nullable=True)
    tool_name = Column(String(100), nullable=False)
    tool_args = Column(JSON, nullable=False, default=dict)
    tool_result = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="complete")  # complete|error
    created_at = Column(DateTime(timezone=True), server_default=func.now())
