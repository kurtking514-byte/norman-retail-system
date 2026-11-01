"""add is_paid to repair_requests

Revision ID: e5a9c2d7b1f4
Revises: c4e8a1f3d2b7
Create Date: 2026-11-01 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a9c2d7b1f4'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1f3d2b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Track whether each repair has been paid (existing rows start unpaid)."""
    op.add_column(
        'repair_requests',
        sa.Column('is_paid', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Drop is_paid."""
    with op.batch_alter_table('repair_requests') as batch_op:
        batch_op.drop_column('is_paid')
