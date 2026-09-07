from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from plotlot.storage.model_base import Base


class PortfolioEntry(Base):
    __tablename__ = "portfolio_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    address: Mapped[str] = mapped_column(String, nullable=False)
    municipality: Mapped[str] = mapped_column(String, nullable=False)
    county: Mapped[str] = mapped_column(String, nullable=False)
    zoning_district: Mapped[str | None] = mapped_column(String, nullable=True)
    report_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReportCache(Base):
    __tablename__ = "report_cache"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "address_normalized",
            "analysis_type",
            name="uq_report_cache_tenant_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    address: Mapped[str] = mapped_column(String, nullable=False, index=True)
    address_normalized: Mapped[str] = mapped_column(String, nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False, default="residential")
    report_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)


class ConnectorCredential(Base):
    __tablename__ = "connector_credentials"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "session_id",
            name="uq_connector_credentials_tenant_session",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_username: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_password_enc: Mapped[str] = mapped_column(Text, nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    daily_send_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    send_count_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
