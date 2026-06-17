"""add resume and job description columns

Revision ID: 0002_add_resume_and_jd_columns
Revises: 0001_create_sessions_table
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_add_resume_and_jd_columns"
down_revision = "0001_create_sessions_table"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sessions", sa.Column("resume_filename", sa.String(length=255), nullable=True))
    op.add_column("sessions", sa.Column("resume_text", sa.String(), nullable=True))
    op.add_column("sessions", sa.Column("job_description", sa.String(), nullable=True))


def downgrade():
    op.drop_column("sessions", "job_description")
    op.drop_column("sessions", "resume_text")
    op.drop_column("sessions", "resume_filename")
