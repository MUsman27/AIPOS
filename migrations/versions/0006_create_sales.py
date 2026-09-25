"""create sales and sale_items tables

Revision ID: 0006_sales
Revises: 0005_customer_discount
Create Date: 2026-09-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_sales"
down_revision: Union[str, None] = "0005_customer_discount"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sales",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_number", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("sale_date", sa.DateTime(), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("paid_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("change_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("payment_method", sa.String(length=50), nullable=False, server_default="Cash"),
        sa.Column("payment_status", sa.String(length=50), nullable=False, server_default="Paid"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number"),
    )
    op.create_index(op.f("ix_sales_invoice_number"), "sales", ["invoice_number"], unique=True)
    op.create_index(op.f("ix_sales_customer_id"), "sales", ["customer_id"], unique=False)
    op.create_index(op.f("ix_sales_sale_date"), "sales", ["sale_date"], unique=False)

    op.create_table(
        "sale_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_name", sa.String(length=500), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("cost_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False, server_default="1.00"),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("line_total", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sale_items_sale_id"), "sale_items", ["sale_id"], unique=False)
    op.create_index(op.f("ix_sale_items_product_id"), "sale_items", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sale_items_product_id"), table_name="sale_items")
    op.drop_index(op.f("ix_sale_items_sale_id"), table_name="sale_items")
    op.drop_table("sale_items")

    op.drop_index(op.f("ix_sales_sale_date"), table_name="sales")
    op.drop_index(op.f("ix_sales_customer_id"), table_name="sales")
    op.drop_index(op.f("ix_sales_invoice_number"), table_name="sales")
    op.drop_table("sales")
