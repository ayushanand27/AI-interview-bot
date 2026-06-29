"""Schemas for recruiter dashboard API."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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
    proctoring_summary: Optional[dict[str, Any]] = None
    low_identity_confidence: bool = False
    identity_similarity_score: Optional[float] = None
    human_review_flag: bool = False
    recording_available: bool = False
    recording_filename: Optional[str] = None
    transcript: list[TranscriptItem]


class HumanReviewUpdateRequest(BaseModel):
    flagged: bool
