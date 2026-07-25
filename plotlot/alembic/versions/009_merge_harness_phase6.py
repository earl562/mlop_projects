"""Merge the harness and phase6 branches into a single head.

Revision ID: 009
Revises: 008, 008_lineage
Create Date: 2026-07-08

After 006 the history forked into two branches that both (incorrectly) reused
the revision ids "007" and "008":

  * harness branch:  006 -> 007 (harness_core) -> 008 (harness_artifact)
  * phase6 branch:   006 -> d3e4f5a6b7c8 (connector) -> 007_phase6 -> 008_lineage

The duplicate ids made the graph unresolvable, so migrations were never run and
the app fell back to Base.metadata.create_all (which is what let the live schema
drift, e.g. workspaces.owner_user_id). The phase6 branch ids were renamed to be
unique; this pure merge revision joins both branch heads so `alembic upgrade
head` has a single, well-defined target again. It performs no DDL.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, Sequence[str], None] = ("008", "008_lineage")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: this revision only reconciles the two branch heads."""


def downgrade() -> None:
    """No-op: splitting back into two heads is not supported."""
