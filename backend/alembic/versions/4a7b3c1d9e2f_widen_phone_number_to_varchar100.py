"""widen phone_number to VARCHAR(100)

Revision ID: 4a7b3c1d9e2f
Revises: d8d4fbc3394e
Create Date: 2026-07-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a7b3c1d9e2f'
down_revision: Union[str, Sequence[str], None] = 'd8d4fbc3394e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen phone_number from VARCHAR(20) to VARCHAR(100)."""
    op.alter_column(
        'customers',
        'phone_number',
        existing_type=sa.String(length=20),
        type_=sa.String(length=100),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert phone_number back to VARCHAR(20)."""
    op.alter_column(
        'customers',
        'phone_number',
        existing_type=sa.String(length=100),
        type_=sa.String(length=20),
        existing_nullable=False,
    )