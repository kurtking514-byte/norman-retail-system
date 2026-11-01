"""make product brand, category, model number and prices optional

Revision ID: 7e1f2a9c4b3d
Revises: 4a7b3c1d9e2f
Create Date: 2026-11-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e1f2a9c4b3d'
down_revision: Union[str, Sequence[str], None] = '4a7b3c1d9e2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = {
    'brand_id': sa.Integer(),
    'category_id': sa.Integer(),
    'model_number': sa.String(length=100),
    'cost_price': sa.DECIMAL(10, 2),
    'selling_price': sa.DECIMAL(10, 2),
}


def upgrade() -> None:
    """Allow products to be saved without these fields."""
    with op.batch_alter_table('products') as batch:
        for name, type_ in COLUMNS.items():
            batch.alter_column(name, existing_type=type_, nullable=True)


def downgrade() -> None:
    """Make the fields required again (fails if any product is missing them)."""
    with op.batch_alter_table('products') as batch:
        for name, type_ in COLUMNS.items():
            batch.alter_column(name, existing_type=type_, nullable=False)
