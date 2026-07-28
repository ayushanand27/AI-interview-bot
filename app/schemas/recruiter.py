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
    invite_token: Optional[str] = None


class RecruiterSessionFilters(BaseModel):
    role_title: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    invite_token: Optional[str] = None
    score_band: Optional[str] = None
    integrity_level: Optional[str] = None
    review_status: Optional[str] = None


class InviteFunnelMetrics(BaseModel):
    created: int = 0
    opened: int = 0
    registered: int = 0
    verified: int = 0
    started: int = 0
    completed: int = 0


class AssessmentPerformanceMetric(BaseModel):
    token: str
    role_preview: str
    difficulty: str
    question_count: int
    used_count: int
    started_count: int
    completed_count: int
    average_score: Optional[float] = None
    integrity_flag_count: int = 0
    created_at: datetime


class RecruiterAnalyticsResponse(BaseModel):
    generated_at: datetime
    invite_count: int = 0
    completed_session_count: int = 0
    completion_rate_percent: float = 0.0
    average_score: Optional[float] = None
    integrity_flag_rate_percent: float = 0.0
    review_flagged_count: int = 0
    funnel: InviteFunnelMetrics = Field(default_factory=InviteFunnelMetrics)
    score_distribution: dict[str, int] = Field(default_factory=dict)
    integrity_distribution: dict[str, int] = Field(default_factory=dict)
    assessments: list[AssessmentPerformanceMetric] = Field(default_factory=list)


class TranscriptItem(BaseModel):
    index: int
    question: str
    answer: Optional[str] = None
    judgment: Optional[dict[str, Any]] = None
    is_adaptive_follow_up: bool = False
    adaptive_topic: Optional[str] = None
    adaptive_source: Optional[str] = None


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
    adaptive_interview: Optional[dict[str, Any]] = None


class HumanReviewUpdateRequest(BaseModel):
    flagged: bool


class RecruiterReviewUpdateRequest(BaseModel):
    review_status: Literal["needs_review", "in_review", "cleared", "escalated", "rejected"]
    review_notes: Optional[str] = None
