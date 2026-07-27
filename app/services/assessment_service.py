"""Recruiter assessment creation — JD-only question generation via Groq."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictException, NotFoundException
from app.db.interview_invite_model import InterviewInvite
from app.schemas.recruiter_assessment import (
    AssessmentQuestion,
    AssessmentSummary,
    CreateAssessmentRequest,
    CreateAssessmentResponse,
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    UpdateAssessmentRequest,
)
from app.services.groq_client import get_groq_client
from app.services.question_utils import (
    default_time_seconds,
    normalize_questions,
    question_text,
)


def _as_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _strip_markdown_code_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def _extract_question_text(item: object) -> str:
    return question_text(item)


def _questions_from_payload(payload: object) -> list[str]:
    if isinstance(payload, list):
        return [_extract_question_text(item) for item in payload]

    if isinstance(payload, dict):
        questions = payload.get("questions", payload.get("items", []))
        if isinstance(questions, list):
            return [_extract_question_text(item) for item in questions]

    return []


def _questions_from_newlines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.startswith(("-", "*")):
            cleaned = cleaned[1:].strip()
        if len(cleaned) > 2 and cleaned[0].isdigit() and cleaned[1] in (".", ")"):
            cleaned = cleaned[2:].strip()
        if cleaned and not cleaned.startswith("{") and not cleaned.startswith("["):
            lines.append(cleaned)
    return lines


def _fallback_questions(jd_text: str, question_count: int, difficulty: str) -> list[str]:
    role_hint = jd_text.strip().splitlines()[0][:120] if jd_text.strip() else "this role"
    templates = [
        f"Based on the job description for {role_hint}, what relevant experience do you bring to this {difficulty.lower()} position?",
        "Describe a project where you applied skills mentioned in the job description. What was your contribution?",
        "How do you approach learning new tools or frameworks required for a role like this?",
        "Walk me through how you debug and resolve a production issue under time pressure.",
        "Tell me about a time you collaborated with others to deliver a feature end to end.",
        "How do you write maintainable, testable code in a fast-moving team?",
        "Describe a technical decision you made, the tradeoffs you considered, and the outcome.",
        "How do you prioritize tasks when multiple stakeholders have competing deadlines?",
        "Explain a complex technical concept from the job description as you would to a non-technical stakeholder.",
        "What metrics or outcomes do you use to judge whether your work was successful?",
        "Describe a situation where you received critical feedback and how you responded.",
        "How do you ensure security, performance, and reliability in your implementations?",
        "Tell me about a time you had to refactor legacy code. What was your strategy?",
        "How do you document and communicate your design decisions to the team?",
        "What interests you most about the responsibilities described in this job description?",
        "Describe your experience with the primary technologies mentioned in the job description.",
        "How do you validate requirements before starting implementation?",
        "Tell me about a mistake you made in a project and what you learned from it.",
        "How do you mentor or support teammates with less experience?",
        "Why are you a strong fit for this position based on the job description?",
    ]
    return [templates[i % len(templates)] for i in range(question_count)]


def _parse_questions_from_llm_text(
    content: str,
    question_count: int,
    jd_text: str,
    difficulty: str,
) -> list[str]:
    text = _strip_markdown_code_block(content)

    cleaned: list[str] = []
    try:
        payload = json.loads(text)
        cleaned = [q for q in _questions_from_payload(payload) if q]
    except json.JSONDecodeError:
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = text.find(opener), text.rfind(closer) + 1
            if start >= 0 and end > start:
                try:
                    payload = json.loads(text[start:end])
                    cleaned = [q for q in _questions_from_payload(payload) if q]
                    if cleaned:
                        break
                except json.JSONDecodeError:
                    continue

    if not cleaned:
        cleaned = [q for q in _questions_from_newlines(text) if q]

    if not cleaned:
        cleaned = _fallback_questions(jd_text, question_count, difficulty)

    return cleaned[:question_count] or _fallback_questions(jd_text, question_count, difficulty)


def generate_questions_from_jd(
    jd_text: str,
    question_count: int,
    difficulty: str,
) -> list[str]:
    """Generate unbiased interview questions from a job description only."""
    system_prompt = (
        "You are a senior technical interviewer. "
        "Generate clear, concise interview questions based ONLY on the job description. "
        "Do not assume any candidate resume or background. "
        "Each question must be answerable in 2-4 minutes. "
        "Do not include numbering prefixes in the question text."
    )
    user_prompt = (
        f"Difficulty level: {difficulty}\n"
        f"Number of questions: {question_count}\n\n"
        f"Job Description:\n{jd_text.strip()}\n\n"
        "Return ONLY valid JSON in this shape:\n"
        '{"questions": ["question 1", "question 2"]}'
    )

    content = ""
    try:
        response = get_groq_client().chat.completions.create(
            model=settings.GROQ_MODEL,
            temperature=0.6,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ""
    except Exception:
        return _fallback_questions(jd_text, question_count, difficulty)

    if not content.strip():
        return _fallback_questions(jd_text, question_count, difficulty)

    return _parse_questions_from_llm_text(content, question_count, jd_text, difficulty)


def _to_assessment_questions(raw: list) -> list[AssessmentQuestion]:
    normalized = normalize_questions(raw)
    return [
        AssessmentQuestion(
            text=q["text"],
            time_seconds=int(q["time_seconds"]),
            marks=float(q["marks"]),
        )
        for q in normalized
    ]


def _questions_payload(questions: list[AssessmentQuestion]) -> list[dict]:
    return [
        {
            "text": q.text,
            "time_seconds": q.time_seconds,
            "marks": q.marks,
        }
        for q in questions
    ]


def _summary_from_invite(invite: InterviewInvite, now: datetime) -> AssessmentSummary:
    jd_lines = invite.jd_text.strip().splitlines()
    role_preview = (jd_lines[0][:80] if jd_lines else "Assessment").strip()
    questions = normalize_questions(list(invite.questions_json or []))
    expiry = _as_aware_utc(invite.expiry_at)
    created = _as_aware_utc(invite.created_at)
    return AssessmentSummary(
        token=invite.token,
        invite_link=f"/interview/invite/{invite.token}",
        role_preview=role_preview,
        difficulty=invite.difficulty,
        question_count=len(questions),
        expiry_at=expiry,
        used_count=invite.used_count,
        max_uses=invite.max_uses,
        created_at=created,
        is_expired=expiry <= now,
    )


class AssessmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def generate_questions_preview(
        data: GenerateQuestionsRequest,
    ) -> GenerateQuestionsResponse:
        raw = generate_questions_from_jd(
            data.jd_text,
            data.question_count,
            data.difficulty,
        )
        default_time = default_time_seconds()
        questions = [
            AssessmentQuestion(text=text, time_seconds=default_time, marks=10)
            for text in raw
            if text.strip()
        ]
        return GenerateQuestionsResponse(questions=questions, jd_text=data.jd_text)

    async def create_assessment(
        self,
        recruiter_id: int,
        data: CreateAssessmentRequest,
    ) -> CreateAssessmentResponse:
        if data.questions:
            questions = data.questions
        else:
            raw = generate_questions_from_jd(
                data.jd_text,
                data.question_count,
                data.difficulty,
            )
            questions = _to_assessment_questions(raw)

        token = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expiry_at = now + timedelta(hours=data.expiry_hours)

        invite = InterviewInvite(
            token=token,
            recruiter_id=recruiter_id,
            jd_text=data.jd_text,
            questions_json=_questions_payload(questions),
            difficulty=data.difficulty,
            expiry_at=expiry_at,
            max_uses=100,
            used_count=0,
            created_at=now,
        )
        self.db.add(invite)
        await self.db.commit()

        invite_link = f"/interview/invite/{token}"
        return CreateAssessmentResponse(
            token=token,
            invite_link=invite_link,
            questions_preview=questions,
        )

    async def list_assessments(self, recruiter_id: int) -> list[AssessmentSummary]:
        result = await self.db.execute(
            select(InterviewInvite)
            .where(InterviewInvite.recruiter_id == recruiter_id)
            .order_by(InterviewInvite.created_at.desc())
        )
        now = datetime.now(timezone.utc)
        return [_summary_from_invite(row, now) for row in result.scalars().all()]

    async def delete_assessment(self, recruiter_id: int, token: str) -> None:
        result = await self.db.execute(
            select(InterviewInvite).where(InterviewInvite.token == token)
        )
        invite = result.scalar_one_or_none()
        if invite is None or invite.recruiter_id != recruiter_id:
            raise NotFoundException("Assessment not found")
        if invite.used_count > 0:
            raise ConflictException(
                "Cannot delete an assessment that has already been used by a candidate."
            )
        await self.db.delete(invite)
        await self.db.commit()

    async def update_assessment(
        self,
        recruiter_id: int,
        token: str,
        data: UpdateAssessmentRequest,
    ) -> AssessmentSummary:
        result = await self.db.execute(
            select(InterviewInvite).where(InterviewInvite.token == token)
        )
        invite = result.scalar_one_or_none()
        if invite is None or invite.recruiter_id != recruiter_id:
            raise NotFoundException("Assessment not found")
        if data.expiry_hours is not None:
            invite.expiry_at = datetime.now(timezone.utc) + timedelta(
                hours=data.expiry_hours
            )
        await self.db.commit()
        await self.db.refresh(invite)
        now = datetime.now(timezone.utc)
        return _summary_from_invite(invite, now)
