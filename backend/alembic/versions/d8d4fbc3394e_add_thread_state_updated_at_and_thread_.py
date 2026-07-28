"""add thread_state_updated_at and thread_state_pinned

Revision ID: d8d4fbc3394e
Revises: 6ad4080275d7
Create Date: 2026-07-24 15:00:53.754738

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8d4fbc3394e'
down_revision: Union[str, Sequence[str], None] = '6ad4080275d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('customers', sa.Column('thread_state_updated_at', sa.DateTime(), nullable=True))
    op.add_column('customers', sa.Column('thread_state_pinned', sa.Boolean(), nullable=True))
    op.execute("UPDATE customers SET thread_state_pinned = 0 WHERE thread_state_pinned IS NULL")
    # Set thread_state_updated_at to created_at for existing rows as a best-effort default
    op.execute("UPDATE customers SET thread_state_updated_at = created_at WHERE thread_state_updated_at IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('customers', 'thread_state_pinned')
    op.drop_column('customers', 'thread_state_updated_at')
