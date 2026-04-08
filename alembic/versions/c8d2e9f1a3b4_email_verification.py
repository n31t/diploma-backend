"""Email verification: users.is_verified, registration_tokens.user_id.

Revision ID: c8d2e9f1a3b4
Revises: a3f1b2c4d5e6
Create Date: 20260608 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d2e9f1a3b4"
down_revision: Union[str, Sequence[str], None] = "a3f1b2c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Existing accounts stay usable without going through email flow.
    op.execute(sa.text("UPDATE users SET is_verified = true"))

    op.execute(
        sa.text("ALTER TABLE registration_tokens RENAME COLUMN created_by TO user_id")
    )
    op.create_index(
        op.f("ix_registration_tokens_user_id"),
        "registration_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_registration_tokens_user_id"),
        table_name="registration_tokens",
    )
    op.execute(
        sa.text("ALTER TABLE registration_tokens RENAME COLUMN user_id TO created_by")
    )
    op.drop_column("users", "is_verified")
