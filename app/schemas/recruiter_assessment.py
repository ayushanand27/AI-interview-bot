"""Schemas for recruiter JD-based assessment creation."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CreateAssessmentRequest(BaseModel):
    jd_text: str = Field(..., min_length=20)
    question_count: int
    difficulty: str
    expiry_hours: int

    @field_validator("question_count")
    @classmethod
    def validate_question_count(cls, v: int) -> int:
        if not (2 <= v <= 20):
            raise ValueError("question_count must be between 2 and 20")
        return v

    @field_validator("expiry_hours")
    @classmethod
    def validate_expiry_hours(cls, v: int) -> int:
        if v not in (24, 48, 72, 168):
            raise ValueError("expiry_hours must be 24, 48, 72, or 168")
        return v

    @field_validator("difficulty")
    @classmethod
    def normalize_difficulty(cls, v: str) -> str:
        allowed = {"easy", "medium", "hard"}
        normalized = v.strip().lower()
        if normalized not in allowed:
            raise ValueError("difficulty must be Easy, Medium, or Hard")
        return normalized.capitalize()

    @field_validator("jd_text")
    @classmethod
    def jd_not_empty(cls, v: str) -> str:
        text = v.strip()
        if len(text) < 20:
            raise ValueError("Job description must be at least 20 characters")
        return text


class CreateAssessmentResponse(BaseModel):
    token: str
    invite_link: str
    questions_preview: list[str]


class ParseJdPdfResponse(BaseModel):
    jd_text: str


class AssessmentSummary(BaseModel):
    token: str
    invite_link: str
    role_preview: str
    difficulty: str
    question_count: int
    expiry_at: datetime
    used_count: int
    max_uses: int
    created_at: datetime
    is_expired: bool


class UpdateAssessmentRequest(BaseModel):
    expiry_hours: int | None = None

    @field_validator("expiry_hours")
    @classmethod
    def validate_expiry_hours(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v not in (24, 48, 72, 168):
            raise ValueError("expiry_hours must be 24, 48, 72, or 168")
        return v

