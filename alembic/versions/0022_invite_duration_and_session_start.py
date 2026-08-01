"""add invite duration_minutes and session interview_started_at

Revision ID: 0022_invite_duration_session_start
Revises: 0021_add_jobs_and_live_rooms
Create Date: 2026-08-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0022_invite_duration_session_start"
down_revision = "0021_add_jobs_and_live_rooms"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    invite_cols = _columns("interview_invites")
    if "duration_minutes" not in invite_cols:
        op.add_column(
            "interview_invites",
            sa.Column("duration_minutes", sa.Integer(), nullable=True),
        )

    session_cols = _columns("sessions")
    if "interview_started_at" not in session_cols:
        op.add_column(
            "sessions",
            sa.Column("interview_started_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    session_cols = _columns("sessions")
    if "interview_started_at" in session_cols:
        op.drop_column("sessions", "interview_started_at")

    invite_cols = _columns("interview_invites")
    if "duration_minutes" in invite_cols:
        op.drop_column("interview_invites", "duration_minutes")
