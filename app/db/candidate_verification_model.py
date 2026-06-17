"""ORM model for invite candidate identity verification records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CandidateVerification(Base):
    __tablename__ = "candidate_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_invites.token"),
        nullable=False,
        index=True,
    )
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    id_document_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    selfie_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
