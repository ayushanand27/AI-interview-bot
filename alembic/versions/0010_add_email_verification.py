"""add email verification and password reset columns to users

Revision ID: 0010_add_email_verification
Revises: 0009_add_candidate_verifications
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_add_email_verification"
down_revision = "0009_add_candidate_verifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}

    if "is_verified" not in columns:
        op.add_column(
            "users",
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "verification_token" not in columns:
        op.add_column(
            "users",
            sa.Column("verification_token", sa.String(length=36), nullable=True),
        )
    if "verification_token_expiry" not in columns:
        op.add_column(
            "users",
            sa.Column("verification_token_expiry", sa.DateTime(timezone=True), nullable=True),
        )
    if "reset_token" not in columns:
        op.add_column(
            "users",
            sa.Column("reset_token", sa.String(length=36), nullable=True),
        )
    if "reset_token_expiry" not in columns:
        op.add_column(
            "users",
            sa.Column("reset_token_expiry", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}

    if "reset_token_expiry" in columns:
        op.drop_column("users", "reset_token_expiry")
    if "reset_token" in columns:
        op.drop_column("users", "reset_token")
    if "verification_token_expiry" in columns:
        op.drop_column("users", "verification_token_expiry")
    if "verification_token" in columns:
        op.drop_column("users", "verification_token")
    if "is_verified" in columns:
        op.drop_column("users", "is_verified")
