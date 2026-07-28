"""Schemas for recruiter dashboard API."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RecruiterReviewState(BaseModel):
    human_review_required: bool = False
    review_status: str = "pending"
    review_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by_user_id: Optional[int] = None


class RecruiterIdentityVerificationMetadata(BaseModel):
    verified: Optional[bool] = None
    confidence_score: Optional[float] = None
    low_identity_confidence: bool = False
    similarity_score: Optional[float] = None
    liveness_mode: Optional[str] = None
    liveness_confidence: Optional[float] = None
    ocr_name: Optional[str] = None
    ocr_document_number: Optional[str] = None
    ocr_confidence: Optional[float] = None
    ocr_name_match: Optional[bool] = None
    message: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    evidence_metadata: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None


class RecruiterProctorEvent(BaseModel):
    type: str
    severity: str
    time: float
    penalty_percent: float = 0.0
    message: str = ""
    evidence_metadata: Optional[dict[str, Any]] = None


class RecruiterSessionSummary(BaseModel):
    session_id: UUID
    candidate_name: str
    role_title: str
    date: datetime = Field(description="Interview completion time (updated_at)")
    final_score: Optional[float] = None
    recommendation: Optional[str] = None
    status: str
    recording_available: bool = False
    human_review_flag: bool = False
    review_status: str = "pending"
    review_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    integrity_level: Optional[str] = None
    integrity_event_count: int = 0
    low_identity_confidence: bool = False


class TranscriptItem(BaseModel):
    index: int
    question: str
    answer: Optional[str] = None
    judgment: Optional[dict[str, Any]] = None


class RecruiterSessionDetail(BaseModel):
    session_id: UUID
    candidate_name: str
    role_title: str
    experience_level: str
    status: str
    date: datetime
    created_at: datetime
    duration_minutes: Optional[int] = None
    total_questions: int
    answered_count: int
    final_score: Optional[dict[str, Any]] = None
    original_score: Optional[float] = None
    adjusted_score: Optional[float] = None
    integrity_penalty_percent: float = 0.0
    integrity_level: Optional[str] = None
    integrity_event_count: int = 0
    proctoring_summary: Optional[dict[str, Any]] = None
    low_identity_confidence: bool = False
    identity_similarity_score: Optional[float] = None
    human_review_flag: bool = False
    review_state: RecruiterReviewState
    identity_verification: Optional[RecruiterIdentityVerificationMetadata] = None
    proctor_events: list[RecruiterProctorEvent] = Field(default_factory=list)
    recording_available: bool = False
    recording_filename: Optional[str] = None
    transcript: list[TranscriptItem]


class HumanReviewUpdateRequest(BaseModel):
    flagged: bool


class RecruiterReviewUpdateRequest(BaseModel):
    review_status: Literal["needs_review", "in_review", "cleared", "escalated", "rejected"]
    review_notes: Optional[str] = None
