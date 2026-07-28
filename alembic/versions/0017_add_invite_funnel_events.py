"""add invite funnel events for recruiter analytics

Revision ID: 0017_add_invite_funnel_events
Revises: 0016_add_phase2_identity_metadata
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_add_invite_funnel_events"
down_revision = "0016_add_phase2_identity_metadata"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    if "invite_funnel_events" in _table_names():
        return

    op.create_table(
        "invite_funnel_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("invite_token", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_email", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invite_token"], ["interview_invites.token"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_invite_funnel_events_invite_token",
        "invite_funnel_events",
        ["invite_token"],
    )
    op.create_index(
        "ix_invite_funnel_events_event_type",
        "invite_funnel_events",
        ["event_type"],
    )
    op.create_index(
        "ix_invite_funnel_events_session_id",
        "invite_funnel_events",
        ["session_id"],
    )
    op.create_index(
        "ix_invite_funnel_events_created_at",
        "invite_funnel_events",
        ["created_at"],
    )


def downgrade() -> None:
    if "invite_funnel_events" not in _table_names():
        return
    op.drop_index("ix_invite_funnel_events_created_at", table_name="invite_funnel_events")
    op.drop_index("ix_invite_funnel_events_session_id", table_name="invite_funnel_events")
    op.drop_index("ix_invite_funnel_events_event_type", table_name="invite_funnel_events")
    op.drop_index("ix_invite_funnel_events_invite_token", table_name="invite_funnel_events")
    op.drop_table("invite_funnel_events")
