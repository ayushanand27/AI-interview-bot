"""add human_review_flag to sessions

Revision ID: 0012_add_human_review_flag
Revises: 0011_add_candidate_report_email_sent
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_add_human_review_flag"
down_revision = "0011_add_candidate_report_email_sent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "human_review_flag" not in columns:
        op.add_column(
            "sessions",
            sa.Column(
                "human_review_flag",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}
    if "human_review_flag" in columns:
        op.drop_column("sessions", "human_review_flag")
