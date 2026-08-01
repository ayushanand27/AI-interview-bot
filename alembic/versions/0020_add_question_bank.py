"""add question_bank and question_bank_usage tables

Revision ID: 0020_add_question_bank
Revises: 0019_add_invite_deleted_at
Create Date: 2026-08-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_add_question_bank"
down_revision = "0019_add_invite_deleted_at"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    tables = _table_names()
    if "question_bank" not in tables:
        op.create_table(
            "question_bank",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("type", sa.String(length=32), nullable=False),
            sa.Column("difficulty", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("prompt_text", sa.Text(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("skill_tags", sa.JSON(), nullable=False),
            sa.Column("role_tags", sa.JSON(), nullable=False),
            sa.Column("fingerprint", sa.String(length=200), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("quality_score", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )
        op.create_index("ix_question_bank_slug", "question_bank", ["slug"])
        op.create_index("ix_question_bank_type", "question_bank", ["type"])
        op.create_index("ix_question_bank_difficulty", "question_bank", ["difficulty"])
        op.create_index("ix_question_bank_fingerprint", "question_bank", ["fingerprint"])

    tables = _table_names()
    if "question_bank_usage" not in tables:
        op.create_table(
            "question_bank_usage",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("question_id", sa.Integer(), nullable=False),
            sa.Column("recruiter_id", sa.Integer(), nullable=False),
            sa.Column("invite_token", sa.String(length=36), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["question_id"], ["question_bank.id"]),
            sa.ForeignKeyConstraint(["recruiter_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "question_id",
                "invite_token",
                name="uq_question_bank_usage_question_invite",
            ),
        )
        op.create_index(
            "ix_question_bank_usage_question_id",
            "question_bank_usage",
            ["question_id"],
        )
        op.create_index(
            "ix_question_bank_usage_recruiter_id",
            "question_bank_usage",
            ["recruiter_id"],
        )
        op.create_index(
            "ix_question_bank_usage_invite_token",
            "question_bank_usage",
            ["invite_token"],
        )
        op.create_index(
            "ix_question_bank_usage_used_at",
            "question_bank_usage",
            ["used_at"],
        )


def downgrade() -> None:
    tables = _table_names()
    if "question_bank_usage" in tables:
        op.drop_table("question_bank_usage")
    if "question_bank" in tables:
        op.drop_table("question_bank")
