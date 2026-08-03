"""Add district_dimensional_standards and workspace_members.clerk_organization_id.

Revision ID: 019_dim_standards_clerk_org
Revises: 018_ordinance_chunks_updated_at
Create Date: 2026-08-03

Closes the last two gaps between the ORM models and the migration chain, found
by the startup drift check after running the full chain against a copy of
production.

Both objects are declared by models on the production-MVP branch but were never
represented in a migration, so they only existed on databases built by
`Base.metadata.create_all`:

* `district_dimensional_standards` backs the verified-fact dimensional-standard
  path in `pipeline/lookup.py` — the typed row that replaces LLM-extracted
  numeric params and grades the result local_authority rather than assumption.
  Its own model docstring says "provisioned by versioned Alembic migrations",
  which is what this revision finally makes true. Without the table the lookup
  catches the failure and silently falls back to LLM extraction, so the feature
  degrades invisibly rather than erroring.
* `workspace_members.clerk_organization_id` maps a workspace member to their
  Clerk organization.

Guarded so it is safe on a database that already has either object.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_dim_standards_clerk_org"
down_revision: Union[str, None] = "018_ordinance_chunks_updated_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_table("district_dimensional_standards"):
        op.create_table(
            "district_dimensional_standards",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("municipality", sa.String(length=200), nullable=False),
            sa.Column("county", sa.String(length=100), nullable=False),
            sa.Column("state", sa.String(length=2), nullable=True),
            sa.Column("district_code", sa.String(length=40), nullable=False),
            sa.Column("min_lot_area_sqft", sa.Float(), nullable=True),
            sa.Column("min_lot_width_ft", sa.Float(), nullable=True),
            sa.Column("setback_front_ft", sa.Float(), nullable=True),
            sa.Column("setback_side_ft", sa.Float(), nullable=True),
            sa.Column("setback_rear_ft", sa.Float(), nullable=True),
            sa.Column("max_height_ft", sa.Float(), nullable=True),
            sa.Column("max_lot_coverage_pct", sa.Float(), nullable=True),
            sa.Column("far", sa.Float(), nullable=True),
            sa.Column("max_density_units_per_acre", sa.Float(), nullable=True),
            sa.Column(
                "source_section_id", sa.String(length=300), nullable=False, server_default=""
            ),
            sa.Column("source_url", sa.Text(), nullable=True),
            sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "verification_status",
                sa.String(length=20),
                nullable=True,
                server_default="unverified",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.UniqueConstraint(
                "municipality", "district_code", name="uq_district_dimensional_standard"
            ),
        )
        for column in ("municipality", "county", "district_code", "verification_status"):
            op.create_index(
                op.f(f"ix_district_dimensional_standards_{column}"),
                "district_dimensional_standards",
                [column],
            )

    if not _has_column("workspace_members", "clerk_organization_id"):
        op.add_column(
            "workspace_members",
            sa.Column("clerk_organization_id", sa.String(length=120), nullable=True),
        )
        op.create_index(
            op.f("ix_workspace_members_clerk_organization_id"),
            "workspace_members",
            ["clerk_organization_id"],
        )


def downgrade() -> None:
    if _has_column("workspace_members", "clerk_organization_id"):
        op.drop_index(
            op.f("ix_workspace_members_clerk_organization_id"), table_name="workspace_members"
        )
        op.drop_column("workspace_members", "clerk_organization_id")
    if _has_table("district_dimensional_standards"):
        for column in ("verification_status", "district_code", "county", "municipality"):
            op.drop_index(
                op.f(f"ix_district_dimensional_standards_{column}"),
                table_name="district_dimensional_standards",
            )
        op.drop_table("district_dimensional_standards")
