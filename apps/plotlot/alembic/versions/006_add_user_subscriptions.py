"""Add user_subscriptions table for Clerk+Stripe billing.

Revision ID: 006
Revises: 88d5f65b958d
Create Date: 2026-03-25

Adds user_subscriptions to track Clerk user plan (free/pro), Stripe
customer/subscription IDs, monthly analysis usage counter, and billing
period dates.  Free tier: 5 analyses/month. Pro tier: unlimited.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "88d5f65b958d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_subscriptions",
        sa.Column("user_id", sa.String(), nullable=False, primary_key=True),
        sa.Column("plan", sa.String(), nullable=False, server_default="free"),
        sa.Column("stripe_customer_id", sa.String(), nullable=True, unique=True),
        sa.Column("stripe_subscription_id", sa.String(), nullable=True),
        sa.Column("analyses_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_subscriptions")
