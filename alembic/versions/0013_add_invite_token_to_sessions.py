"""add invite_token to sessions for recruiter tenancy

Revision ID: 0013_add_invite_token_to_sessions
Revises: 0012_add_human_review_flag
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_add_invite_token_to_sessions"
down_revision = "0012_add_human_review_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "invite_token" not in columns:
        op.add_column(
            "sessions",
            sa.Column("invite_token", sa.String(length=36), nullable=True),
        )
        # Backfill from candidate_verifications (invite flow linkage).
        # SQLite Uuid text may omit hyphens; verification.session_id usually has them.
        op.execute(
            """
            UPDATE sessions
            SET invite_token = (
                SELECT candidate_verifications.token
                FROM candidate_verifications
                WHERE REPLACE(LOWER(candidate_verifications.session_id), '-', '')
                    = REPLACE(LOWER(CAST(sessions.session_id AS TEXT)), '-', '')
                LIMIT 1
            )
            WHERE invite_token IS NULL
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}
    if "invite_token" in columns:
        op.drop_column("sessions", "invite_token")
