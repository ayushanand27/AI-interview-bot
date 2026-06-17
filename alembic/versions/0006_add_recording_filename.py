"""add recording_filename to sessions

Revision ID: 0006_add_recording_filename
Revises: 0005_add_user_id_to_sessions
Create Date: 2026-06-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_recording_filename"
down_revision = "0005_add_user_id_to_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "recording_filename" not in columns:
        op.add_column(
            "sessions",
            sa.Column("recording_filename", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}
    if "recording_filename" in columns:
        op.drop_column("sessions", "recording_filename")
