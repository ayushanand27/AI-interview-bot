"""Schemas for recruiter JD-based assessment creation."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.question_utils import (
    DEFAULT_QUESTION_MARKS,
    MAX_ASSESSMENT_QUESTIONS,
    MIN_ASSESSMENT_QUESTIONS,
    QUESTION_TYPES,
    SUPPORTED_CODING_LANGS,
    default_time_seconds,
)
from app.services.coding_judge import LANGUAGE_STARTERS

QuestionType = Literal["subjective", "mcq", "msq", "numerical", "coding"]


class CodingTestCase(BaseModel):
    stdin: str = ""
    expected_stdout: str = ""

    @field_validator("stdin", "expected_stdout", mode="before")
    @classmethod
    def coerce_str(cls, v: object) -> str:
        return "" if v is None else str(v)


class AssessmentQuestion(BaseModel):
    text: str = Field(..., min_length=3)
    type: QuestionType = "subjective"
    options: list[str] | None = None
    correct_indices: list[int] | None = None
    correct_answer: str | None = None
    tolerance: float | None = None
    languages: list[str] | None = None
    starter_code: dict[str, str] | None = None
    public_tests: list[CodingTestCase] | None = None
    hidden_tests: list[CodingTestCase] | None = None
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None
    rubric_notes: str | None = None
    time_seconds: int = Field(default_factory=default_time_seconds)
    marks: float = Field(default=DEFAULT_QUESTION_MARKS)
    bank_id: int | None = None
    origin: Literal["library", "ai"] | None = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        text = v.strip()
        if len(text) < 3:
            raise ValueError("Question text must be at least 3 characters")
        return text

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: object) -> str:
        if v is None or v == "":
            return "subjective"
        normalized = str(v).strip().lower()
        if normalized not in QUESTION_TYPES:
            raise ValueError(
                "type must be one of: subjective, mcq, msq, numerical, coding"
            )
        return normalized

    @field_validator("options", mode="before")
    @classmethod
    def clean_options(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("options must be a list of strings")
        cleaned = [str(item).strip() for item in v if str(item).strip()]
        return cleaned or None

    @field_validator("correct_indices", mode="before")
    @classmethod
    def clean_indices(cls, v: object) -> list[int] | None:
        if v is None:
            return None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return [int(v)]
        if not isinstance(v, list):
            raise ValueError("correct_indices must be a list of integers")
        out: list[int] = []
        for item in v:
            try:
                idx = int(item)
            except (TypeError, ValueError) as exc:
                raise ValueError("correct_indices must be integers") from exc
            if idx not in out:
                out.append(idx)
        return out

    @field_validator("correct_answer", mode="before")
    @classmethod
    def clean_correct_answer(cls, v: object) -> str | None:
        if v is None:
            return None
        text = str(v).strip()
        return text or None

    @field_validator("tolerance", mode="before")
    @classmethod
    def clean_tolerance(cls, v: object) -> float | None:
        if v is None or v == "":
            return None
        try:
            value = float(v)
        except (TypeError, ValueError) as exc:
            raise ValueError("tolerance must be a number") from exc
        if value < 0:
            raise ValueError("tolerance must be >= 0")
        return value

    @field_validator("languages", mode="before")
    @classmethod
    def clean_languages(cls, v: object) -> list[str] | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            parts = [p.strip().lower() for p in v.split(",") if p.strip()]
        elif isinstance(v, list):
            parts = [str(p).strip().lower() for p in v if str(p).strip()]
        else:
            raise ValueError("languages must be a list")
        aliases = {"c++": "cpp", "py": "python", "python3": "python", "js": "javascript"}
        out: list[str] = []
        for part in parts:
            key = aliases.get(part, part)
            if key not in SUPPORTED_CODING_LANGS:
                raise ValueError(
                    f"Unsupported coding language '{part}'. "
                    f"Allowed: {', '.join(SUPPORTED_CODING_LANGS)}"
                )
            if key not in out:
                out.append(key)
        return out or None

    @field_validator("starter_code", mode="before")
    @classmethod
    def clean_starter_code(cls, v: object) -> dict[str, str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            return {"python": v} if v.strip() else None
        if not isinstance(v, dict):
            raise ValueError("starter_code must be a language→source map")
        aliases = {"c++": "cpp", "py": "python", "python3": "python", "js": "javascript"}
        out: dict[str, str] = {}
        for key, value in v.items():
            lang = aliases.get(str(key).strip().lower(), str(key).strip().lower())
            if lang in SUPPORTED_CODING_LANGS and value is not None:
                out[lang] = str(value)
        return out or None

    @field_validator("public_tests", "hidden_tests", mode="before")
    @classmethod
    def clean_tests(cls, v: object) -> list[dict[str, str]] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("tests must be a list")
        out: list[dict[str, str]] = []
        for item in v:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "stdin": str(item.get("stdin", item.get("input", "")) or ""),
                    "expected_stdout": str(
                        item.get(
                            "expected_stdout",
                            item.get("expected", item.get("output", "")),
                        )
                        or ""
                    ),
                }
            )
        return out

    @field_validator("time_limit_ms", mode="before")
    @classmethod
    def clean_time_limit(cls, v: object) -> int | None:
        if v is None or v == "":
            return None
        try:
            value = int(v)
        except (TypeError, ValueError) as exc:
            raise ValueError("time_limit_ms must be an integer") from exc
        if not (500 <= value <= 5000):
            raise ValueError("time_limit_ms must be between 500 and 5000")
        return value

    @field_validator("memory_limit_mb", mode="before")
    @classmethod
    def clean_memory_limit(cls, v: object) -> int | None:
        if v is None or v == "":
            return None
        try:
            value = int(v)
        except (TypeError, ValueError) as exc:
            raise ValueError("memory_limit_mb must be an integer") from exc
        if not (32 <= value <= 256):
            raise ValueError("memory_limit_mb must be between 32 and 256")
        return value

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

    @model_validator(mode="after")
    def validate_by_type(self) -> "AssessmentQuestion":
        if self.type in ("mcq", "msq"):
            options = self.options or []
            if len(options) < 2:
                raise ValueError(f"{self.type.upper()} requires at least 2 options")
            if len(options) > 8:
                raise ValueError(f"{self.type.upper()} allows at most 8 options")
            indices = self.correct_indices or []
            if not indices:
                raise ValueError(f"{self.type.upper()} requires correct_indices")
            if any(i < 0 or i >= len(options) for i in indices):
                raise ValueError("correct_indices must refer to valid options")
            if self.type == "mcq" and len(indices) != 1:
                raise ValueError("MCQ requires exactly one correct index")
            if self.type == "msq" and len(indices) < 1:
                raise ValueError("MSQ requires at least one correct index")
            self.correct_answer = None
            self.tolerance = None
            self.languages = None
            self.starter_code = None
            self.public_tests = None
            self.hidden_tests = None
        elif self.type == "numerical":
            if not self.correct_answer:
                raise ValueError("Numerical questions require correct_answer")
            try:
                float(str(self.correct_answer).replace(",", "").strip())
            except ValueError as exc:
                raise ValueError(
                    "correct_answer must be a number for numerical questions"
                ) from exc
            self.options = None
            self.correct_indices = None
            if self.tolerance is None:
                self.tolerance = 0.0
            self.languages = None
            self.starter_code = None
            self.public_tests = None
            self.hidden_tests = None
        elif self.type == "coding":
            langs = self.languages or ["python"]
            self.languages = langs
            starters = dict(self.starter_code or {})
            for lang in langs:
                if lang not in starters or not str(starters[lang]).strip():
                    starters[lang] = LANGUAGE_STARTERS.get(lang, "")
            self.starter_code = starters
            self.public_tests = self.public_tests or []
            self.hidden_tests = self.hidden_tests or []
            if self.time_limit_ms is None:
                self.time_limit_ms = 2000
            if self.memory_limit_mb is None:
                self.memory_limit_mb = 128
            # Coding questions often need longer timers
            if self.time_seconds < 300:
                self.time_seconds = max(self.time_seconds, 600)
            self.options = None
            self.correct_indices = None
            self.correct_answer = None
            self.tolerance = None
        else:
            self.options = None
            self.correct_indices = None
            self.correct_answer = None
            self.tolerance = None
            self.languages = None
            self.starter_code = None
            self.public_tests = None
            self.hidden_tests = None
        return self


class GenerateQuestionsRequest(BaseModel):
    jd_text: str = Field(..., min_length=20)
    question_count: int
    difficulty: str
    question_types: list[QuestionType] | None = None
    use_question_bank: bool = True

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

    @field_validator("question_types", mode="before")
    @classmethod
    def normalize_question_types(cls, v: object) -> list[str] | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            parts = [p.strip().lower() for p in v.split(",") if p.strip()]
        elif isinstance(v, list):
            parts = [str(p).strip().lower() for p in v if str(p).strip()]
        else:
            raise ValueError("question_types must be a list")
        cleaned: list[str] = []
        for part in parts:
            if part not in QUESTION_TYPES:
                raise ValueError(
                    "question_types entries must be subjective, mcq, msq, numerical, or coding"
                )
            if part not in cleaned:
                cleaned.append(part)
        return cleaned or None


class GenerateQuestionsResponse(BaseModel):
    questions: list[AssessmentQuestion]
    jd_text: str = ""


class CreateAssessmentRequest(BaseModel):
    jd_text: str = Field(..., min_length=20)
    question_count: int
    difficulty: str
    expiry_hours: int
    questions: list[AssessmentQuestion] | None = None
    question_types: list[QuestionType] | None = None
    max_uses: int = Field(default=100, ge=1, le=100)
    duration_minutes: int | None = Field(default=None)

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

    @field_validator("max_uses")
    @classmethod
    def validate_max_uses(cls, v: int) -> int:
        if not (1 <= v <= 100):
            raise ValueError("max_uses must be between 1 and 100")
        return v

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration_minutes(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if not (5 <= v <= 480):
            raise ValueError("duration_minutes must be between 5 and 480, or omitted")
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

    @field_validator("question_types", mode="before")
    @classmethod
    def normalize_question_types(cls, v: object) -> list[str] | None:
        return GenerateQuestionsRequest.normalize_question_types(v)

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
    duration_minutes: int | None = None


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


class SendAssessmentInvitesRequest(BaseModel):
    emails: list[str] = Field(..., min_length=1, max_length=50)
    message: str | None = Field(None, max_length=1000)

    @field_validator("emails", mode="before")
    @classmethod
    def normalize_emails(cls, v: object) -> list[str]:
        if isinstance(v, str):
            parts = [p.strip() for p in re.split(r"[,;\n]+", v) if p.strip()]
        elif isinstance(v, list):
            parts = [str(p).strip() for p in v if str(p).strip()]
        else:
            raise ValueError("emails must be a list or comma/newline-separated string")
        cleaned: list[str] = []
        for email in parts:
            lower = email.lower()
            if "@" not in lower or "." not in lower.split("@")[-1]:
                raise ValueError(f"Invalid email: {email}")
            if lower not in cleaned:
                cleaned.append(lower)
        if not cleaned:
            raise ValueError("At least one email is required")
        if len(cleaned) > 50:
            raise ValueError("At most 50 emails per send")
        return cleaned

    @field_validator("message", mode="before")
    @classmethod
    def clean_message(cls, v: object) -> str | None:
        if v is None:
            return None
        text = str(v).strip()
        return text or None


class SendAssessmentInvitesResponse(BaseModel):
    sent: int
    failed: list[str] = Field(default_factory=list)
    invite_link: str
    delivery_note: str | None = None
