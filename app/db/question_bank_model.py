"""ORM models for curated assessment question library."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QuestionBankItem(Base):
    __tablename__ = "question_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    skill_tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    role_tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    fingerprint: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="seed")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QuestionBankUsage(Base):
    __tablename__ = "question_bank_usage"
    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "invite_token",
            name="uq_question_bank_usage_question_invite",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("question_bank.id"),
        nullable=False,
        index=True,
    )
    recruiter_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    invite_token: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
