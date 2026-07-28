"""add adaptive_state for Phase 5 interviewing

Revision ID: 0018_add_adaptive_interview_state
Revises: 0017_add_invite_funnel_events
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_add_adaptive_interview_state"
down_revision = "0017_add_invite_funnel_events"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in set(inspector.get_table_names()):
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    cols = _column_names("sessions")
    if not cols or "adaptive_state" in cols:
        return
    op.add_column("sessions", sa.Column("adaptive_state", sa.JSON(), nullable=True))


def downgrade() -> None:
    cols = _column_names("sessions")
    if "adaptive_state" not in cols:
        return
    op.drop_column("sessions", "adaptive_state")
