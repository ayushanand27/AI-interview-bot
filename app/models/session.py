"""Interview session domain model."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.models.schemas import SessionStatus


@dataclass
class InterviewSession:
    """Single interview session (memory + data/sessions/*.json)."""

    session_id: UUID
    role_title: str
    experience_level: str
    topic_focus: Optional[str]
    user_id: Optional[int] = None
    candidate_name: str = "Unknown Candidate"
    resume_filename: Optional[str] = None
    resume_text: Optional[str] = None
    job_description: Optional[str] = None
    proctoring_summary: Optional[dict[str, Any]] = None
    status: SessionStatus = SessionStatus.CREATED
    questions: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    # Per-answer judgment objects returned by the judge service
    answer_judgments: list[dict] = field(default_factory=list)
    # Final aggregated score and report (populated on end_interview)
    final_score: dict | None = None
    current_question_index: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_questions(self) -> int:
        return len(self.questions)

    @property
    def is_complete(self) -> bool:
        return (
            self.status == SessionStatus.COMPLETED
            or (
                self.total_questions > 0
                and self.current_question_index >= self.total_questions
            )
        )
