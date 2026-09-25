"""add discount_percent column to customers table

Revision ID: 0005_customer_discount
Revises: 0004_customers
Create Date: 2026-09-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_customer_discount"
down_revision: Union[str, None] = "0004_customers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch:
        batch.add_column(
            sa.Column(
                "discount_percent",
                sa.Numeric(precision=5, scale=2),
                nullable=True,
                server_default="0.00",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("customers") as batch:
        batch.drop_column("discount_percent")
