"""add phase 2 identity verification metadata

Revision ID: 0016_add_phase2_identity_metadata
Revises: 0015_add_structured_evidence_tables
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_add_phase2_identity_metadata"
down_revision = "0015_add_structured_evidence_tables"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _column_names("identity_verification_attempts")

    if "liveness_mode" not in columns:
        op.add_column(
            "identity_verification_attempts",
            sa.Column("liveness_mode", sa.String(length=32), nullable=True),
        )
    if "liveness_confidence" not in columns:
        op.add_column(
            "identity_verification_attempts",
            sa.Column("liveness_confidence", sa.Float(), nullable=True),
        )
    if "ocr_name" not in columns:
        op.add_column(
            "identity_verification_attempts",
            sa.Column("ocr_name", sa.String(length=255), nullable=True),
        )
    if "ocr_document_number" not in columns:
        op.add_column(
            "identity_verification_attempts",
            sa.Column("ocr_document_number", sa.String(length=128), nullable=True),
        )
    if "ocr_confidence" not in columns:
        op.add_column(
            "identity_verification_attempts",
            sa.Column("ocr_confidence", sa.Float(), nullable=True),
        )
    if "evidence_metadata" not in columns:
        op.add_column(
            "identity_verification_attempts",
            sa.Column("evidence_metadata", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    columns = _column_names("identity_verification_attempts")

    if "evidence_metadata" in columns:
        op.drop_column("identity_verification_attempts", "evidence_metadata")
    if "ocr_confidence" in columns:
        op.drop_column("identity_verification_attempts", "ocr_confidence")
    if "ocr_document_number" in columns:
        op.drop_column("identity_verification_attempts", "ocr_document_number")
    if "ocr_name" in columns:
        op.drop_column("identity_verification_attempts", "ocr_name")
    if "liveness_confidence" in columns:
        op.drop_column("identity_verification_attempts", "liveness_confidence")
    if "liveness_mode" in columns:
        op.drop_column("identity_verification_attempts", "liveness_mode")
