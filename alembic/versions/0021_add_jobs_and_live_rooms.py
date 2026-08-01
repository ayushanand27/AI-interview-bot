"""add job_postings, job_applications, live_interview_rooms

Revision ID: 0021_add_jobs_and_live_rooms
Revises: 0020_add_question_bank
Create Date: 2026-08-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_add_jobs_and_live_rooms"
down_revision = "0020_add_question_bank"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "job_postings" not in tables:
        op.create_table(
            "job_postings",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("token", sa.String(length=36), nullable=False),
            sa.Column("recruiter_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("jd_text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["recruiter_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token"),
        )
        op.create_index("ix_job_postings_token", "job_postings", ["token"])
        op.create_index("ix_job_postings_recruiter_id", "job_postings", ["recruiter_id"])
        op.create_index("ix_job_postings_deleted_at", "job_postings", ["deleted_at"])

    tables = _tables()
    if "job_applications" not in tables:
        op.create_table(
            "job_applications",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_id", sa.Integer(), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("resume_storage_key", sa.String(length=512), nullable=True),
            sa.Column("resume_text", sa.Text(), nullable=False),
            sa.Column("ats_score", sa.Float(), nullable=False),
            sa.Column("ats_detail_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["job_id"], ["job_postings.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_job_applications_job_id", "job_applications", ["job_id"])
        op.create_index("ix_job_applications_email", "job_applications", ["email"])
        op.create_index("ix_job_applications_status", "job_applications", ["status"])

    tables = _tables()
    if "live_interview_rooms" not in tables:
        op.create_table(
            "live_interview_rooms",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("token", sa.String(length=36), nullable=False),
            sa.Column("recruiter_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("meet_url", sa.String(length=1024), nullable=True),
            sa.Column("problem_text", sa.Text(), nullable=False),
            sa.Column("starter_code", sa.Text(), nullable=False),
            sa.Column("language", sa.String(length=32), nullable=False),
            sa.Column("public_tests_json", sa.JSON(), nullable=False),
            sa.Column("final_code", sa.Text(), nullable=True),
            sa.Column("notes_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("application_id", sa.Integer(), nullable=True),
            sa.Column("expiry_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["recruiter_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["application_id"], ["job_applications.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token"),
        )
        op.create_index("ix_live_interview_rooms_token", "live_interview_rooms", ["token"])
        op.create_index(
            "ix_live_interview_rooms_recruiter_id", "live_interview_rooms", ["recruiter_id"]
        )
        op.create_index("ix_live_interview_rooms_status", "live_interview_rooms", ["status"])


def downgrade() -> None:
    tables = _tables()
    if "live_interview_rooms" in tables:
        op.drop_table("live_interview_rooms")
    if "job_applications" in tables:
        op.drop_table("job_applications")
    if "job_postings" in tables:
        op.drop_table("job_postings")
