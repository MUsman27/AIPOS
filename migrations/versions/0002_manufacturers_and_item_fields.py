"""manufacturers and item description fields

Revision ID: 0002_items
Revises: 0001_products
Create Date: 2026-09-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_items"
down_revision: Union[str, None] = "0001_products"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manufacturers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_file", sa.String(length=260), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_manufacturers_name"),
    )
    op.create_table(
        "products_new",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("cost_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("manufacturer_id", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("description_ur", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["manufacturer_id"],
            ["manufacturers.id"],
            name="fk_products_manufacturer_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "manufacturer_id",
            "sku",
            name="uq_products_manufacturer_sku",
        ),
    )
    op.execute(
        """
        INSERT INTO products_new (
            id, sku, barcode, name, unit_price, cost_price,
            is_active, created_at, updated_at
        )
        SELECT
            id, sku, barcode, name, unit_price, cost_price,
            is_active, created_at, updated_at
        FROM products
        """
    )
    op.drop_table("products")
    op.rename_table("products_new", "products")
    op.create_index("ix_products_barcode", "products", ["barcode"], unique=True)
    op.create_index("ix_products_manufacturer_id", "products", ["manufacturer_id"])


def downgrade() -> None:
    op.drop_index("ix_products_manufacturer_id", table_name="products")
    op.drop_index("ix_products_barcode", table_name="products")
    op.create_table(
        "products_old",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("cost_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
    )
    op.execute(
        """
        INSERT INTO products_old (
            id, sku, barcode, name, unit_price, cost_price,
            is_active, created_at, updated_at
        )
        SELECT
            id, sku, barcode, substr(name, 1, 200),
            COALESCE(unit_price, 0), cost_price,
            is_active, created_at, updated_at
        FROM products
        """
    )
    op.drop_table("products")
    op.rename_table("products_old", "products")
    op.create_index("ix_products_barcode", "products", ["barcode"], unique=True)
    op.drop_table("manufacturers")
