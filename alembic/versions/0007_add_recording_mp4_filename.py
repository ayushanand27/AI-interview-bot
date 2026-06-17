"""add recording_mp4_filename to sessions

Revision ID: 0007_add_recording_mp4_filename
Revises: 0006_add_recording_filename
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_recording_mp4_filename"
down_revision = "0006_add_recording_filename"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}

    if "recording_mp4_filename" not in columns:
        op.add_column(
            "sessions",
            sa.Column("recording_mp4_filename", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sessions")}
    if "recording_mp4_filename" in columns:
        op.drop_column("sessions", "recording_mp4_filename")
