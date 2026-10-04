"""add account-based licensing

Revision ID: 0008_account_licensing
Revises: 0007_licensing
Create Date: 2026-10-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_account_licensing"
down_revision: Union[str, None] = "0007_licensing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("license_customers", "clients")
    op.add_column("clients", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("clients", sa.Column("address", sa.String(length=500), nullable=True))
    op.add_column(
        "clients",
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
    )
    op.add_column(
        "clients", sa.Column("license_expires_at", sa.DateTime(), nullable=True)
    )
    op.add_column("clients", sa.Column("max_devices", sa.Integer(), nullable=True))
    op.add_column(
        "clients",
        sa.Column(
            "license_features",
            sa.Text(),
            server_default='["sales","inventory","reports"]',
            nullable=False,
        ),
    )

    op.create_table(
        "license_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.String(length=100), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["clients.customer_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_license_users_email"),
    )
    op.create_index("ix_license_users_customer_id", "license_users", ["customer_id"])

    op.create_table(
        "license_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["license_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_license_sessions_user_id", "license_sessions", ["user_id"])
    op.create_index("ix_license_sessions_expires_at", "license_sessions", ["expires_at"])

    op.add_column(
        "licensed_devices",
        sa.Column("registered_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_licensed_devices_registered_by_user_id",
        "licensed_devices",
        "license_users",
        ["registered_by_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_licensed_devices_registered_by_user_id",
        "licensed_devices",
        ["registered_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_licensed_devices_registered_by_user_id", table_name="licensed_devices"
    )
    op.drop_constraint(
        "fk_licensed_devices_registered_by_user_id",
        "licensed_devices",
        type_="foreignkey",
    )
    op.drop_column("licensed_devices", "registered_by_user_id")

    op.drop_index("ix_license_sessions_expires_at", table_name="license_sessions")
    op.drop_index("ix_license_sessions_user_id", table_name="license_sessions")
    op.drop_table("license_sessions")

    op.drop_index("ix_license_users_customer_id", table_name="license_users")
    op.drop_table("license_users")

    op.drop_column("clients", "license_features")
    op.drop_column("clients", "max_devices")
    op.drop_column("clients", "license_expires_at")
    op.drop_column("clients", "is_active")
    op.drop_column("clients", "address")
    op.drop_column("clients", "phone")
    op.rename_table("clients", "license_customers")
