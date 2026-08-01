"""ORM model for recruiter-created interview invite links."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InterviewInvite(Base):
    __tablename__ = "interview_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    recruiter_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    questions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False)
    expiry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Optional overall exam length (minutes). None = per-question timers only.
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
