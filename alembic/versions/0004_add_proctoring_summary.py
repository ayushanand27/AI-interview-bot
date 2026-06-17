"""add proctoring_summary column

Revision ID: 0004_add_proctoring_summary
Revises: 0003_add_judgments_and_final_score
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_proctoring_summary"
down_revision = "0003_add_judgments_and_final_score"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "proctoring_summary" not in columns:
        op.add_column("sessions", sa.Column("proctoring_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "proctoring_summary")
