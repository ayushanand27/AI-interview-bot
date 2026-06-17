"""add candidate_report_email_sent_at to sessions

Revision ID: 0011_add_candidate_report_email_sent
Revises: 0010_add_email_verification
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_add_candidate_report_email_sent"
down_revision = "0010_add_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "candidate_report_email_sent_at" not in columns:
        op.add_column(
            "sessions",
            sa.Column(
                "candidate_report_email_sent_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "candidate_report_email_sent_at" in columns:
        op.drop_column("sessions", "candidate_report_email_sent_at")
