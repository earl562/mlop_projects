"""merge_heads

Revision ID: 88d5f65b958d
Revises: 003, 005
Create Date: 2026-03-11 13:01:30.186592

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88d5f65b958d'
down_revision: Union[str, None] = ('003', '005')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
