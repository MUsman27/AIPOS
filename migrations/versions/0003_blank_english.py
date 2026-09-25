"""allow a blank English description

Revision ID: 0003_blank_english
Revises: 0002_items
Create Date: 2026-09-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_blank_english"
down_revision: Union[str, None] = "0002_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# These lists have one description column, so English was only a copy of it.
_SINGLE_COLUMN_BRANDS = ("MGP", "Perfect Autos", "Power Ride", "Pilot")


def upgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.alter_column(
            "name",
            existing_type=sa.String(length=500),
            nullable=True,
        )
    brands = ", ".join(repr(name) for name in _SINGLE_COLUMN_BRANDS)
    op.execute(
        sa.text(
            "UPDATE products SET name = NULL "
            "WHERE manufacturer_id IN ("
            f"SELECT id FROM manufacturers WHERE name IN ({brands})"
            ")"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE products SET name = COALESCE(description_ur, model, 'Item') "
            "WHERE name IS NULL"
        )
    )
    with op.batch_alter_table("products") as batch:
        batch.alter_column(
            "name",
            existing_type=sa.String(length=500),
            nullable=False,
        )
