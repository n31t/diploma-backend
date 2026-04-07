"""Add Stripe subscription support.

Revision ID: a3f1b2c4d5e6
Revises: b1e4c64104af
Create Date: 2026-04-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3f1b2c4d5e6"
down_revision: Union[str, Sequence[str], None] = "b1e4c64104af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users: add stripe_customer_id ---
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_users_stripe_customer_id"),
        "users",
        ["stripe_customer_id"],
        unique=True,
    )

    # --- subscriptions table ---
    op.create_table(
        "subscriptions",
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="incomplete"),
        sa.Column("plan_type", sa.String(length=30), nullable=False, server_default="premium"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_subscriptions_user_id"), "subscriptions", ["user_id"], unique=True
    )
    op.create_index(
        op.f("ix_subscriptions_stripe_subscription_id"),
        "subscriptions",
        ["stripe_subscription_id"],
        unique=True,
    )

    # --- lower free-tier limits for non-premium users ---
    op.execute(
        "UPDATE user_limits SET daily_limit = 10, monthly_limit = 100 "
        "WHERE is_premium = false"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE user_limits SET daily_limit = 100, monthly_limit = 1000 "
        "WHERE is_premium = false"
    )

    op.drop_index(
        op.f("ix_subscriptions_stripe_subscription_id"), table_name="subscriptions"
    )
    op.drop_index(op.f("ix_subscriptions_user_id"), table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index(op.f("ix_users_stripe_customer_id"), table_name="users")
    op.drop_column("users", "stripe_customer_id")
