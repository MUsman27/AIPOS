"""add offline licensing records

Revision ID: 0007_licensing
Revises: 0006_sales
Create Date: 2026-09-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_licensing"
down_revision: Union[str, None] = "0006_sales"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "license_customers",
        sa.Column("customer_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("customer_id"),
    )
    op.create_table(
        "licensed_devices",
        sa.Column("device_id", sa.String(length=120), nullable=False),
        sa.Column("customer_id", sa.String(length=100), nullable=False),
        sa.Column("device_public_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["license_customers.customer_id"]),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_index("ix_licensed_devices_customer_id", "licensed_devices", ["customer_id"])
    op.create_table(
        "issued_licenses",
        sa.Column("license_id", sa.String(length=120), nullable=False),
        sa.Column("device_id", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["licensed_devices.device_id"]),
        sa.PrimaryKeyConstraint("license_id"),
    )
    op.create_index("ix_issued_licenses_device_id", "issued_licenses", ["device_id"])
    op.create_index("ix_issued_licenses_expires_at", "issued_licenses", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_issued_licenses_expires_at", table_name="issued_licenses")
    op.drop_index("ix_issued_licenses_device_id", table_name="issued_licenses")
    op.drop_table("issued_licenses")
    op.drop_index("ix_licensed_devices_customer_id", table_name="licensed_devices")
    op.drop_table("licensed_devices")
    op.drop_table("license_customers")