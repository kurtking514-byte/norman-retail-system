"""add created_at to repair_requests

Revision ID: c4e8a1f3d2b7
Revises: 9b2d5e7f1a6c
Create Date: 2026-11-01 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1f3d2b7'
down_revision: Union[str, Sequence[str], None] = '9b2d5e7f1a6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Record when each repair came in (existing rows use their last update)."""
    op.add_column('repair_requests', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.execute("UPDATE repair_requests SET created_at = updated_at WHERE created_at IS NULL")


def downgrade() -> None:
    """Drop created_at."""
    op.drop_column('repair_requests', 'created_at')
