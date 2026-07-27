"""Schemas for recruiter JD-based assessment creation."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.question_utils import (
    DEFAULT_QUESTION_MARKS,
    MAX_ASSESSMENT_QUESTIONS,
    MIN_ASSESSMENT_QUESTIONS,
    default_time_seconds,
)


class AssessmentQuestion(BaseModel):
    text: str = Field(..., min_length=3)
    time_seconds: int = Field(default_factory=default_time_seconds)
    marks: float = Field(default=DEFAULT_QUESTION_MARKS)

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        text = v.strip()
        if len(text) < 3:
            raise ValueError("Question text must be at least 3 characters")
        return text

    @field_validator("time_seconds")
    @classmethod
    def validate_time(cls, v: int) -> int:
        if not (30 <= v <= 3600):
            raise ValueError("time_seconds must be between 30 and 3600")
        return v

    @field_validator("marks")
    @classmethod
    def validate_marks(cls, v: float) -> float:
        if not (0.5 <= v <= 100):
            raise ValueError("marks must be between 0.5 and 100")
        return float(v)


class GenerateQuestionsRequest(BaseModel):
    jd_text: str = Field(..., min_length=20)
    question_count: int
    difficulty: str

    @field_validator("question_count")
    @classmethod
    def validate_question_count(cls, v: int) -> int:
        if not (MIN_ASSESSMENT_QUESTIONS <= v <= MAX_ASSESSMENT_QUESTIONS):
            raise ValueError(
                f"question_count must be between {MIN_ASSESSMENT_QUESTIONS} and {MAX_ASSESSMENT_QUESTIONS}"
            )
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


class GenerateQuestionsResponse(BaseModel):
    questions: list[AssessmentQuestion]
    jd_text: str = ""


class CreateAssessmentRequest(BaseModel):
    jd_text: str = Field(..., min_length=20)
    question_count: int
    difficulty: str
    expiry_hours: int
    questions: list[AssessmentQuestion] | None = None

    @field_validator("question_count")
    @classmethod
    def validate_question_count(cls, v: int) -> int:
        if not (MIN_ASSESSMENT_QUESTIONS <= v <= MAX_ASSESSMENT_QUESTIONS):
            raise ValueError(
                f"question_count must be between {MIN_ASSESSMENT_QUESTIONS} and {MAX_ASSESSMENT_QUESTIONS}"
            )
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

    @model_validator(mode="after")
    def validate_custom_questions(self) -> "CreateAssessmentRequest":
        if self.questions is None:
            return self
        count = len(self.questions)
        if count < MIN_ASSESSMENT_QUESTIONS:
            raise ValueError(
                f"At least {MIN_ASSESSMENT_QUESTIONS} questions are required"
            )
        if count > MAX_ASSESSMENT_QUESTIONS:
            raise ValueError(
                f"At most {MAX_ASSESSMENT_QUESTIONS} questions are allowed"
            )
        return self


class CreateAssessmentResponse(BaseModel):
    token: str
    invite_link: str
    questions_preview: list[AssessmentQuestion]


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
