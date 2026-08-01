"""Pydantic schemas for API requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SessionStatus(str, Enum):
    """Lifecycle states for an interview session."""

    CREATED = "created"
    QUESTIONS_READY = "questions_ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ENDED = "ended"
    ABANDONED = "abandoned"


class InterviewSessionCreate(BaseModel):
    """Optional metadata when creating a session (future: resume, JD)."""

    role_title: str = Field(
        default="Software Engineer",
        description="Target role for technical questions.",
        examples=["Backend Developer"],
    )
    experience_level: str = Field(
        default="mid",
        description="junior | mid | senior",
        examples=["mid"],
    )
    topic_focus: Optional[str] = Field(
        default=None,
        description="Optional focus area, e.g. Python, system design.",
        examples=["FastAPI"],
    )


class InterviewSessionResponse(BaseModel):
    session_id: UUID = Field(
        description="Use this exact value in all /sessions/{session_id}/... endpoints.",
    )
    status: SessionStatus
    role_title: str
    experience_level: str
    topic_focus: Optional[str] = None
    total_questions: int = 0
    current_question_index: int = 0
    created_at: datetime


class FetchJdUrlRequest(BaseModel):
    url: str = Field(..., min_length=8, description="Public job posting URL")


class FetchJdUrlResponse(BaseModel):
    jd_text: str
    source: str


class GenerateQuestionsRequest(BaseModel):
    """Override question count per session if needed."""

    question_count: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description="Number of questions to generate (defaults to env setting).",
    )


class GenerateQuestionsResponse(BaseModel):
    session_id: UUID
    status: SessionStatus
    total_questions: int
    message: str


class CurrentQuestionResponse(BaseModel):
    session_id: UUID
    status: SessionStatus
    question_index: int
    total_questions: int
    question: Optional[str] = None
    is_complete: bool = False
    message: str
    proctor_warning_count: int = Field(
        0,
        description="Current proctoring strike count for this interview session.",
    )
    time_seconds: Optional[int] = Field(
        None,
        description="Per-question timer in seconds (from assessment config when set).",
    )
    marks: Optional[float] = Field(
        None,
        description="Per-question scoring weight / max marks when configured.",
    )
    question_type: Optional[str] = Field(
        "subjective",
        description="subjective | mcq | msq | numerical | coding",
    )
    options: Optional[list[str]] = Field(
        None,
        description="Shuffled options for MCQ/MSQ (correct keys never included).",
    )
    tolerance: Optional[float] = Field(
        None,
        description="Allowed absolute error for numerical questions (hint only).",
    )
    languages: Optional[list[str]] = Field(
        None,
        description="Allowed languages for coding questions.",
    )
    starter_code: Optional[dict[str, str]] = Field(
        None,
        description="Starter templates keyed by language for coding questions.",
    )
    public_tests: Optional[list[dict[str, str]]] = Field(
        None,
        description="Candidate-visible sample tests (stdin / expected_stdout).",
    )
    time_limit_ms: Optional[int] = Field(
        None,
        description="Per-test CPU time limit for coding questions (ms).",
    )
    memory_limit_mb: Optional[int] = Field(
        None,
        description="Per-test memory limit for coding questions (MB).",
    )
    is_adaptive_follow_up: bool = Field(
        False,
        description="True when this question was adapted from prior answer quality (Phase 5).",
    )
    adaptive_topic: Optional[str] = Field(
        None,
        description="Coverage topic for the current adaptive/seed question when available.",
    )
    adaptive_difficulty: Optional[str] = Field(
        None,
        description="Difficulty band for the current question when adaptive interviewing is active.",
    )


class AnswerSubmitRequest(BaseModel):
    answer: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Candidate answer to the current question (max 2000 characters).",
        examples=["I would use dependency injection to keep services testable."],
    )

    @field_validator("answer")
    @classmethod
    def normalize_answer(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Answer cannot be empty.")
        if len(stripped) > 2000:
            raise ValueError("Answer exceeds the 2000 character limit.")
        return stripped


class CodingAnswerRequest(BaseModel):
    language: str = Field(..., min_length=1, max_length=32)
    source: str = Field(..., min_length=1, max_length=100_000)

    @field_validator("language")
    @classmethod
    def normalize_language(cls, v: str) -> str:
        from app.services.coding_judge import normalize_coding_language

        normalized = normalize_coding_language(v)
        if not normalized:
            raise ValueError(
                "language must be one of: c, cpp, python, perl, java, javascript"
            )
        return normalized

    @field_validator("source")
    @classmethod
    def normalize_source(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("source cannot be empty.")
        if len(v) > 100_000:
            raise ValueError("source exceeds the 100000 character limit.")
        return v


class CodingRunPublicRequest(BaseModel):
    language: str = Field(..., min_length=1, max_length=32)
    source: str = Field(..., min_length=1, max_length=100_000)

    @field_validator("language")
    @classmethod
    def normalize_language(cls, v: str) -> str:
        from app.services.coding_judge import normalize_coding_language

        normalized = normalize_coding_language(v)
        if not normalized:
            raise ValueError(
                "language must be one of: c, cpp, python, perl, java, javascript"
            )
        return normalized

    @field_validator("source")
    @classmethod
    def normalize_source(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("source cannot be empty.")
        if len(v) > 100_000:
            raise ValueError("source exceeds the 100000 character limit.")
        return v


class CodingRunPublicResponse(BaseModel):
    session_id: UUID
    question_index: int
    passed: int
    total: int
    error: Optional[str] = None
    cases: list[dict] = Field(default_factory=list)


class AnswerSubmitResponse(BaseModel):
    session_id: UUID
    status: SessionStatus
    answered_question_index: int
    message: str
    has_more_questions: bool
    is_complete: bool
    remaining_questions: int = Field(
        description="How many questions still need GET current-question + POST answers.",
    )


class AudioTranscribeResponse(BaseModel):
    """Whisper transcription only — review in UI, then POST /answers."""

    session_id: UUID
    transcribed_text: str


class AudioAnswerResponse(AnswerSubmitResponse):
    """Transcription plus full answer submit (same fields as text answer)."""

    transcribed_text: str = Field(
        description="Text produced by Whisper from the uploaded audio.",
    )


class EndInterviewResponse(BaseModel):
    session_id: UUID
    status: SessionStatus
    total_questions: int
    answered_count: int
    unanswered_count: int = Field(
        description="Questions generated but never answered before end.",
    )
    questions: list[str]
    answers: list[str]
    # Optional judge/evaluation results
    answer_judgments: Optional[list[dict]] = None
    final_score: Optional[dict] = None
    message: str
    original_score: Optional[float] = None
    integrity_penalty_percent: float = 0.0
    adjusted_final_score: Optional[float] = None
    integrity_report: Optional[dict] = None
    integrity_level: Optional[str] = None
    candidate_report_email_sent: bool = False


class RecordingUploadResponse(BaseModel):
    session_id: UUID
    recording_filename: str
    message: str = "Recording saved successfully"
