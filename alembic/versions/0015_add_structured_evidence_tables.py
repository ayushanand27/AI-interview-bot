"""add structured evidence, artifact, and review tables

Revision ID: 0015_add_structured_evidence_tables
Revises: 0014_backfill_invite_token_uuid
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_add_structured_evidence_tables"
down_revision = "0014_backfill_invite_token_uuid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "session_artifacts" not in tables:
        op.create_table(
            "session_artifacts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.Uuid(), sa.ForeignKey("sessions.session_id"), nullable=True),
            sa.Column(
                "candidate_verification_id",
                sa.Integer(),
                sa.ForeignKey("candidate_verifications.id"),
                nullable=True,
            ),
            sa.Column("artifact_type", sa.String(length=64), nullable=False),
            sa.Column("storage_path", sa.String(length=512), nullable=True),
            sa.Column("mime_type", sa.String(length=128), nullable=True),
            sa.Column("file_size_bytes", sa.Integer(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_session_artifacts_session_id",
            "session_artifacts",
            ["session_id"],
            unique=False,
        )
        op.create_index(
            "ix_session_artifacts_candidate_verification_id",
            "session_artifacts",
            ["candidate_verification_id"],
            unique=False,
        )
        op.create_index(
            "ix_session_artifacts_artifact_type",
            "session_artifacts",
            ["artifact_type"],
            unique=False,
        )

    if "proctor_events" not in tables:
        op.create_table(
            "proctor_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.Uuid(), sa.ForeignKey("sessions.session_id"), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("severity", sa.String(length=32), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("penalty_percent", sa.Float(), nullable=False),
            sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("evidence_metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_proctor_events_session_id", "proctor_events", ["session_id"], unique=False)
        op.create_index("ix_proctor_events_event_type", "proctor_events", ["event_type"], unique=False)

    if "identity_verification_attempts" not in tables:
        op.create_table(
            "identity_verification_attempts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "candidate_verification_id",
                sa.Integer(),
                sa.ForeignKey("candidate_verifications.id"),
                nullable=False,
            ),
            sa.Column(
                "token",
                sa.String(length=36),
                sa.ForeignKey("interview_invites.token"),
                nullable=False,
            ),
            sa.Column("session_id", sa.String(length=36), nullable=True),
            sa.Column("verified", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column(
                "low_identity_confidence",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("similarity_score", sa.Float(), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("id_artifact_id", sa.Integer(), sa.ForeignKey("session_artifacts.id"), nullable=True),
            sa.Column(
                "selfie_artifact_id",
                sa.Integer(),
                sa.ForeignKey("session_artifacts.id"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_identity_verification_attempts_candidate_verification_id",
            "identity_verification_attempts",
            ["candidate_verification_id"],
            unique=False,
        )
        op.create_index(
            "ix_identity_verification_attempts_token",
            "identity_verification_attempts",
            ["token"],
            unique=False,
        )
        op.create_index(
            "ix_identity_verification_attempts_session_id",
            "identity_verification_attempts",
            ["session_id"],
            unique=False,
        )

    if "session_review_states" not in tables:
        op.create_table(
            "session_review_states",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "session_id",
                sa.Uuid(),
                sa.ForeignKey("sessions.session_id"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "human_review_required",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "review_status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("review_notes", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_session_review_states_session_id",
            "session_review_states",
            ["session_id"],
            unique=True,
        )

    # Backfill baseline review state for already-flagged sessions.
    op.execute(
        """
        INSERT INTO session_review_states (
            session_id,
            human_review_required,
            review_status,
            review_notes,
            reviewed_at,
            reviewed_by_user_id,
            created_at,
            updated_at
        )
        SELECT
            session_id,
            1,
            'needs_review',
            NULL,
            NULL,
            NULL,
            updated_at,
            updated_at
        FROM sessions
        WHERE human_review_flag = 1
          AND session_id NOT IN (
              SELECT session_id FROM session_review_states
          )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "session_review_states" in tables:
        op.drop_index("ix_session_review_states_session_id", table_name="session_review_states")
        op.drop_table("session_review_states")

    if "identity_verification_attempts" in tables:
        op.drop_index(
            "ix_identity_verification_attempts_session_id",
            table_name="identity_verification_attempts",
        )
        op.drop_index(
            "ix_identity_verification_attempts_token",
            table_name="identity_verification_attempts",
        )
        op.drop_index(
            "ix_identity_verification_attempts_candidate_verification_id",
            table_name="identity_verification_attempts",
        )
        op.drop_table("identity_verification_attempts")

    if "proctor_events" in tables:
        op.drop_index("ix_proctor_events_event_type", table_name="proctor_events")
        op.drop_index("ix_proctor_events_session_id", table_name="proctor_events")
        op.drop_table("proctor_events")

    if "session_artifacts" in tables:
        op.drop_index("ix_session_artifacts_artifact_type", table_name="session_artifacts")
        op.drop_index(
            "ix_session_artifacts_candidate_verification_id",
            table_name="session_artifacts",
        )
        op.drop_index("ix_session_artifacts_session_id", table_name="session_artifacts")
        op.drop_table("session_artifacts")
