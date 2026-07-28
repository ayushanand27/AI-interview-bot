"""ORM model for persisted interview sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    experience_level: Mapped[str] = mapped_column(String(50), nullable=False)
    topic_focus: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    questions: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    answers: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    current_question_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Extended fields used by the interview flow (see Alembic migrations)
    resume_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resume_text: Mapped[str | None] = mapped_column(String, nullable=True)
    job_description: Mapped[str | None] = mapped_column(String, nullable=True)
    answer_judgments: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    final_score: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    proctoring_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    recording_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recording_mp4_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_report_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    human_review_flag: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    # Set when the session was started via a recruiter invite link.
    invite_token: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # Phase 5: adaptive interview blueprint / coverage / adaptation log.
    adaptive_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
