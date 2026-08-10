"""add current_refresh_jti to users for refresh-token rotation/revocation

Revision ID: 0023_add_refresh_token_jti
Revises: 0022_invite_duration_session_start
Create Date: 2026-08-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_add_refresh_token_jti"
down_revision = "0022_invite_duration_session_start"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    user_cols = _columns("users")
    if "current_refresh_jti" not in user_cols:
        op.add_column(
            "users",
            sa.Column("current_refresh_jti", sa.String(length=36), nullable=True),
        )


def downgrade() -> None:
    user_cols = _columns("users")
    if "current_refresh_jti" in user_cols:
        op.drop_column("users", "current_refresh_jti")
