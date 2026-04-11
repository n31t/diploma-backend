"""Telegram user preferences: detection language and UI locale.

Revision ID: f1a2b3c4d5e7
Revises: e7f8a9b0c1d2
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e7"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("telegram_detection_language", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("telegram_ui_locale", sa.String(length=5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "telegram_ui_locale")
    op.drop_column("users", "telegram_detection_language")
