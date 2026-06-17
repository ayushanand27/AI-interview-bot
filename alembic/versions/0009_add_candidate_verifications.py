"""add candidate_verifications table

Revision ID: 0009_add_candidate_verifications
Revises: 0008_create_interview_invites
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_add_candidate_verifications"
down_revision = "0008_create_interview_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidate_verifications" in inspector.get_table_names():
        return

    op.create_table(
        "candidate_verifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(length=36), nullable=False),
        sa.Column("candidate_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("id_document_path", sa.String(length=512), nullable=True),
        sa.Column("selfie_path", sa.String(length=512), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["token"], ["interview_invites.token"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_candidate_verifications_token"),
        "candidate_verifications",
        ["token"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "candidate_verifications" not in inspector.get_table_names():
        return
    op.drop_index(
        op.f("ix_candidate_verifications_token"),
        table_name="candidate_verifications",
    )
    op.drop_table("candidate_verifications")
