"""add answer_judgments and final_score columns

Revision ID: 0003_add_judgments_and_final_score
Revises: 0002_add_resume_and_jd_columns
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_judgments_and_final_score"
down_revision = "0002_add_resume_and_jd_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "answer_judgments" not in columns:
        op.add_column(
            "sessions",
            sa.Column("answer_judgments", sa.JSON(), nullable=False, server_default="[]"),
        )
    if "final_score" not in columns:
        op.add_column("sessions", sa.Column("final_score", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "final_score")
    op.drop_column("sessions", "answer_judgments")
