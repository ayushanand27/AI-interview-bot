"""add user_id to sessions

Revision ID: 0005_add_user_id_to_sessions
Revises: 0004_add_proctoring_summary
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_user_id_to_sessions"
down_revision = "0004_add_proctoring_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "user_id" not in columns:
        # SQLite cannot ALTER ADD CONSTRAINT; FK is enforced in the ORM model.
        op.add_column(
            "sessions",
            sa.Column("user_id", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}
    if "user_id" in columns:
        op.drop_column("sessions", "user_id")
