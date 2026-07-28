"""Structured evidence persistence models for sessions and invite verification."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class ProctorEvent(Base):
    __tablename__ = "proctor_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.session_id"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    penalty_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionArtifact(Base):
    __tablename__ = "session_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.session_id"),
        nullable=True,
        index=True,
    )
    candidate_verification_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("candidate_verifications.id"),
        nullable=True,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdentityVerificationAttempt(Base):
    __tablename__ = "identity_verification_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_verification_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("candidate_verifications.id"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_invites.token"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_identity_confidence: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liveness_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    liveness_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ocr_document_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    id_artifact_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("session_artifacts.id"),
        nullable=True,
    )
    selfie_artifact_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("session_artifacts.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionReviewState(Base):
    __tablename__ = "session_review_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.session_id"),
        nullable=False,
        unique=True,
        index=True,
    )
    human_review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
