"""create interview_invites table

Revision ID: 0008_create_interview_invites
Revises: 0007_add_recording_mp4_filename
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_create_interview_invites"
down_revision = "0007_add_recording_mp4_filename"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "interview_invites" in inspector.get_table_names():
        return

    op.create_table(
        "interview_invites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(length=36), nullable=False),
        sa.Column("recruiter_id", sa.Integer(), nullable=False),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("questions_json", sa.JSON(), nullable=False),
        sa.Column("difficulty", sa.String(length=32), nullable=False),
        sa.Column("expiry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recruiter_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_interview_invites_token"),
        "interview_invites",
        ["token"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "interview_invites" not in inspector.get_table_names():
        return
    op.drop_index(op.f("ix_interview_invites_token"), table_name="interview_invites")
    op.drop_table("interview_invites")
