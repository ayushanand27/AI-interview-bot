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
    QUESTION_TYPES,
    default_time_seconds,
    normalize_question,
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


def _distribute_types(question_count: int, types: list[str]) -> list[str]:
    if not types:
        types = ["subjective"]
    cleaned = [t for t in types if t in QUESTION_TYPES]
    if not cleaned:
        cleaned = ["subjective"]
    out: list[str] = []
    for i in range(question_count):
        out.append(cleaned[i % len(cleaned)])
    return out


def _fallback_question_dicts(
    jd_text: str,
    question_count: int,
    difficulty: str,
    question_types: list[str] | None,
) -> list[dict]:
    role_hint = jd_text.strip().splitlines()[0][:120] if jd_text.strip() else "this role"
    type_plan = _distribute_types(question_count, question_types or ["subjective"])
    subjective_bank = [
        f"Based on the job description for {role_hint}, what relevant experience do you bring to this {difficulty.lower()} position?",
        "Describe a project where you applied skills mentioned in the job description. What was your contribution?",
        "How do you approach learning new tools or frameworks required for a role like this?",
        "Walk me through how you debug and resolve a production issue under time pressure.",
        "Tell me about a time you collaborated with others to deliver a feature end to end.",
        "Describe a technical decision you made, the tradeoffs you considered, and the outcome.",
        "How do you prioritize tasks when multiple stakeholders have competing deadlines?",
        "Explain a complex technical concept from the job description as you would to a non-technical stakeholder.",
    ]
    mcq_bank = [
        {
            "text": "Which practice best improves long-term code maintainability?",
            "options": [
                "Clear naming and small focused functions",
                "Copy-pasting proven snippets everywhere",
                "Avoiding code reviews to move faster",
                "Keeping all logic in one module",
            ],
            "correct_indices": [0],
        },
        {
            "text": "What is the primary goal of writing automated tests?",
            "options": [
                "Increase deploy confidence and catch regressions early",
                "Replace all manual QA forever",
                "Make the codebase larger on purpose",
                "Slow down every feature release",
            ],
            "correct_indices": [0],
        },
        {
            "text": "In a production incident, what should you do first?",
            "options": [
                "Stabilize impact and communicate status",
                "Rewrite the system from scratch",
                "Ignore metrics and wait",
                "Delete logs to reduce noise",
            ],
            "correct_indices": [0],
        },
    ]
    msq_bank = [
        {
            "text": "Which of the following improve API reliability? Select all that apply.",
            "options": [
                "Timeouts and retries with backoff",
                "Input validation",
                "Hard-coding secrets in source",
                "Health checks and monitoring",
            ],
            "correct_indices": [0, 1, 3],
        },
        {
            "text": "Which practices support secure software delivery? Select all that apply.",
            "options": [
                "Least-privilege access",
                "Dependency vulnerability scanning",
                "Sharing production credentials in chat",
                "Encrypted secrets storage",
            ],
            "correct_indices": [0, 1, 3],
        },
    ]
    numerical_bank = [
        {
            "text": "A service handles 120 requests/minute. How many requests is that per hour?",
            "correct_answer": "7200",
            "tolerance": 0,
        },
        {
            "text": "An API has p95 latency of 0.25 seconds. What is that latency in milliseconds?",
            "correct_answer": "250",
            "tolerance": 0,
        },
        {
            "text": "A team completes 8 story points in a 2-week sprint. What is average points per week?",
            "correct_answer": "4",
            "tolerance": 0,
        },
    ]

    out: list[dict] = []
    default_time = default_time_seconds()
    for i, qtype in enumerate(type_plan):
        if qtype == "mcq":
            base = mcq_bank[i % len(mcq_bank)]
            out.append(
                {
                    **base,
                    "type": "mcq",
                    "time_seconds": default_time,
                    "marks": 10,
                }
            )
        elif qtype == "msq":
            base = msq_bank[i % len(msq_bank)]
            out.append(
                {
                    **base,
                    "type": "msq",
                    "time_seconds": default_time,
                    "marks": 10,
                }
            )
        elif qtype == "numerical":
            base = numerical_bank[i % len(numerical_bank)]
            out.append(
                {
                    **base,
                    "type": "numerical",
                    "time_seconds": default_time,
                    "marks": 10,
                }
            )
        else:
            out.append(
                {
                    "text": subjective_bank[i % len(subjective_bank)],
                    "type": "subjective",
                    "time_seconds": default_time,
                    "marks": 10,
                }
            )
    return out


def _coerce_raw_question(item: object, fallback_type: str) -> dict | None:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return {
            "text": text,
            "type": "subjective" if fallback_type == "subjective" else fallback_type,
            "time_seconds": default_time_seconds(),
            "marks": 10,
        }
    if not isinstance(item, dict):
        return None
    text = question_text(item)
    if not text:
        return None
    qtype = str(item.get("type") or fallback_type or "subjective").strip().lower()
    if qtype not in QUESTION_TYPES:
        qtype = "subjective"
    payload: dict = {
        "text": text,
        "type": qtype,
        "time_seconds": item.get("time_seconds") or default_time_seconds(),
        "marks": item.get("marks") or 10,
    }
    if qtype in ("mcq", "msq"):
        options = item.get("options") or []
        if isinstance(options, list):
            payload["options"] = [str(o).strip() for o in options if str(o).strip()]
        indices = item.get("correct_indices")
        if indices is None and item.get("correct_index") is not None:
            indices = [item.get("correct_index")]
        if isinstance(indices, list):
            payload["correct_indices"] = indices
        elif isinstance(indices, (int, float)):
            payload["correct_indices"] = [int(indices)]
    if qtype == "numerical":
        payload["correct_answer"] = str(item.get("correct_answer") or "").strip()
        payload["tolerance"] = item.get("tolerance", 0)
    return payload


def _questions_from_payload(payload: object, type_plan: list[str]) -> list[dict]:
    items: list = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        raw = payload.get("questions", payload.get("items", []))
        if isinstance(raw, list):
            items = raw

    out: list[dict] = []
    for i, item in enumerate(items):
        fallback = type_plan[i] if i < len(type_plan) else "subjective"
        coerced = _coerce_raw_question(item, fallback)
        if coerced:
            out.append(coerced)
    return out


def _parse_questions_from_llm_text(
    content: str,
    question_count: int,
    jd_text: str,
    difficulty: str,
    question_types: list[str] | None = None,
) -> list[dict]:
    text = _strip_markdown_code_block(content)
    type_plan = _distribute_types(question_count, question_types or ["subjective"])
    cleaned: list[dict] = []

    try:
        payload = json.loads(text)
        cleaned = _questions_from_payload(payload, type_plan)
    except json.JSONDecodeError:
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = text.find(opener), text.rfind(closer) + 1
            if start >= 0 and end > start:
                try:
                    payload = json.loads(text[start:end])
                    cleaned = _questions_from_payload(payload, type_plan)
                    if cleaned:
                        break
                except json.JSONDecodeError:
                    continue

    validated: list[dict] = []
    for item in cleaned:
        try:
            q = AssessmentQuestion.model_validate(normalize_question(item))
            validated.append(q.model_dump(exclude_none=True))
        except Exception:
            # Downgrade invalid objective items to subjective text-only
            text_only = question_text(item)
            if text_only:
                validated.append(
                    {
                        "text": text_only,
                        "type": "subjective",
                        "time_seconds": default_time_seconds(),
                        "marks": 10,
                    }
                )

    if len(validated) < question_count:
        fallback = _fallback_question_dicts(
            jd_text, question_count, difficulty, question_types
        )
        validated.extend(fallback[len(validated) :])

    return validated[:question_count]


def generate_questions_from_jd(
    jd_text: str,
    question_count: int,
    difficulty: str,
    question_types: list[str] | None = None,
) -> list[dict]:
    """Generate interview questions from a job description only."""
    types = question_types or ["subjective"]
    type_plan = _distribute_types(question_count, types)
    type_counts: dict[str, int] = {}
    for t in type_plan:
        type_counts[t] = type_counts.get(t, 0) + 1
    mix_desc = ", ".join(f"{count} {name}" for name, count in type_counts.items())

    system_prompt = (
        "You are a senior technical interviewer creating assessment questions. "
        "Generate clear questions based ONLY on the job description. "
        "Do not assume any candidate resume. "
        "Support types: subjective (open-ended), mcq (one correct), "
        "msq (multi-select), numerical (exact/tolerance answer). "
        "For mcq/msq provide 4 plausible options and correct_indices. "
        "For numerical provide correct_answer and optional tolerance. "
        "Do not include numbering prefixes in question text."
    )
    user_prompt = (
        f"Difficulty level: {difficulty}\n"
        f"Number of questions: {question_count}\n"
        f"Requested mix: {mix_desc}\n"
        f"Preferred type order (one per question): {type_plan}\n\n"
        f"Job Description:\n{jd_text.strip()}\n\n"
        "Return ONLY valid JSON in this shape:\n"
        "{\n"
        '  "questions": [\n'
        '    {"text": "...", "type": "subjective", "time_seconds": 180, "marks": 10},\n'
        '    {"text": "...", "type": "mcq", "options": ["A","B","C","D"], '
        '"correct_indices": [0], "time_seconds": 120, "marks": 10},\n'
        '    {"text": "...", "type": "msq", "options": ["A","B","C","D"], '
        '"correct_indices": [0,2], "time_seconds": 120, "marks": 10},\n'
        '    {"text": "...", "type": "numerical", "correct_answer": "42", '
        '"tolerance": 0, "time_seconds": 90, "marks": 10}\n'
        "  ]\n"
        "}"
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
        return _fallback_question_dicts(
            jd_text, question_count, difficulty, question_types
        )

    if not content.strip():
        return _fallback_question_dicts(
            jd_text, question_count, difficulty, question_types
        )

    return _parse_questions_from_llm_text(
        content, question_count, jd_text, difficulty, question_types
    )


def _to_assessment_questions(raw: list) -> list[AssessmentQuestion]:
    questions: list[AssessmentQuestion] = []
    for item in normalize_questions(raw):
        try:
            questions.append(AssessmentQuestion.model_validate(item))
        except Exception:
            questions.append(
                AssessmentQuestion(
                    text=item["text"],
                    type="subjective",
                    time_seconds=int(item.get("time_seconds") or default_time_seconds()),
                    marks=float(item.get("marks") or 10),
                )
            )
    return questions


def _questions_payload(questions: list[AssessmentQuestion]) -> list[dict]:
    return [q.model_dump(exclude_none=True) for q in questions]


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
            data.question_types,
        )
        questions = _to_assessment_questions(raw)
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
                data.question_types,
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

        from app.services.invite_funnel import record_invite_funnel_event

        record_invite_funnel_event(
            invite_token=token,
            event_type="created",
            metadata={"difficulty": data.difficulty, "question_count": len(questions)},
        )

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
