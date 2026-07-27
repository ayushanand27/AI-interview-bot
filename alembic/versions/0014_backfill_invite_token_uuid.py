"""backfill invite_token using hyphen-insensitive UUID match

Revision ID: 0014_backfill_invite_token_uuid
Revises: 0013_add_invite_token_to_sessions
Create Date: 2026-07-27
"""

from alembic import op


revision = "0014_backfill_invite_token_uuid"
down_revision = "0013_add_invite_token_to_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite Uuid columns often render without hyphens; verification.session_id uses hyphens.
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
    # Irreversible data backfill.
    pass
