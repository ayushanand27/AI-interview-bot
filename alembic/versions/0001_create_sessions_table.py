"""create sessions table

Revision ID: 0001_create_sessions_table
Revises: 
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_create_sessions_table'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sessions',
        sa.Column('session_id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('role_title', sa.String(length=255), nullable=False),
        sa.Column('experience_level', sa.String(length=50), nullable=False),
        sa.Column('topic_focus', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('questions', sa.JSON, nullable=False),
        sa.Column('answers', sa.JSON, nullable=False),
        sa.Column('answer_judgments', sa.JSON, nullable=False),
        sa.Column('final_score', sa.JSON, nullable=True),
        sa.Column('current_question_index', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_questions', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table('sessions')
