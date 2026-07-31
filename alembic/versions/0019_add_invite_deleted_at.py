"""add deleted_at to interview_invites for soft-delete

Revision ID: 0019_add_invite_deleted_at
Revises: 0018_add_adaptive_interview_state
Create Date: 2026-07-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_add_invite_deleted_at"
down_revision = "0018_add_adaptive_interview_state"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in set(inspector.get_table_names()):
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    cols = _column_names("interview_invites")
    if not cols or "deleted_at" in cols:
        return
    op.add_column(
        "interview_invites",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_interview_invites_deleted_at",
        "interview_invites",
        ["deleted_at"],
    )


def downgrade() -> None:
    cols = _column_names("interview_invites")
    if "deleted_at" not in cols:
        return
    op.drop_index("ix_interview_invites_deleted_at", table_name="interview_invites")
    op.drop_column("interview_invites", "deleted_at")
