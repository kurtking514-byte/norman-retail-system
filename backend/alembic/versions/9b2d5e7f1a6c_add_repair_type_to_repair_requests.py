"""add repair_type to repair_requests

Revision ID: 9b2d5e7f1a6c
Revises: 7e1f2a9c4b3d
Create Date: 2026-11-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b2d5e7f1a6c'
down_revision: Union[str, Sequence[str], None] = '7e1f2a9c4b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store what is being fixed (picked from a list in the admin)."""
    op.add_column('repair_requests', sa.Column('repair_type', sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Drop repair_type."""
    op.drop_column('repair_requests', 'repair_type')
