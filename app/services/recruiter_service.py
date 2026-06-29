"""Recruiter queries over completed interview sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.db.session_model import Session as DBSession
from app.schemas.recruiter import RecruiterSessionDetail, RecruiterSessionSummary, TranscriptItem
from app.services.report_service import generate_session_report_pdf, report_filename

COMPLETED_STATUSES = ("completed", "ended")


def _candidate_display_name(resume_filename: Optional[str]) -> str:
    if not resume_filename or not resume_filename.strip():
        return "Unknown Candidate"
    stem = Path(resume_filename).stem
    if not stem:
        return "Unknown Candidate"
    return stem.replace("_", " ").replace("-", " ").strip().title()


def _extract_final_score(final_score: Optional[dict[str, Any]]) -> tuple[Optional[float], Optional[str]]:
    if not final_score:
        return None, None
    score = final_score.get("final_score")
    if score is None:
        score = final_score.get("candidate_score")
    recommendation = final_score.get("recommendation")
    if isinstance(score, (int, float)):
        return float(score), recommendation if isinstance(recommendation, str) else None
    return None, recommendation if isinstance(recommendation, str) else None


def _extract_original_score(final_score: Optional[dict[str, Any]]) -> Optional[float]:
    if not final_score:
        return None
    raw = final_score.get("original_score")
    if raw is None:
        raw = final_score.get("final_score")
    if raw is None:
        raw = final_score.get("candidate_score")
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _extract_adjusted_score(final_score: Optional[dict[str, Any]]) -> Optional[float]:
    if not final_score:
        return None
    raw = final_score.get("adjusted_final_score")
    if raw is None:
        raw = final_score.get("final_score")
    if raw is None:
        raw = final_score.get("candidate_score")
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _duration_minutes(row: DBSession) -> Optional[int]:
    if row.created_at and row.updated_at:
        delta = row.updated_at - row.created_at
        return max(int(delta.total_seconds() // 60), 1)
    return None


def _human_review_flag(row: DBSession) -> bool:
    if bool(getattr(row, "human_review_flag", False)):
        return True
    proctoring = row.proctoring_summary if isinstance(row.proctoring_summary, dict) else {}
    if proctoring.get("low_identity_confidence"):
        return True
    level = proctoring.get("integrity_level")
    return level in ("moderate_concerns", "serious_concerns")


def _session_to_summary(row: DBSession) -> RecruiterSessionSummary:
    score, recommendation = _extract_final_score(row.final_score)
    return RecruiterSessionSummary(
        session_id=row.session_id,
        candidate_name=_candidate_display_name(row.resume_filename),
        role_title=row.role_title,
        date=row.updated_at,
        final_score=score,
        recommendation=recommendation,
        status=row.status,
        recording_available=bool(row.recording_filename),
        human_review_flag=_human_review_flag(row),
    )


def _session_to_detail(row: DBSession) -> RecruiterSessionDetail:
    questions = list(row.questions or [])
    answers = list(row.answers or [])
    judgments = list(row.answer_judgments or [])
    proctoring = row.proctoring_summary if isinstance(row.proctoring_summary, dict) else None

    transcript: list[TranscriptItem] = []
    for i, question in enumerate(questions):
        answer = answers[i] if i < len(answers) else None
        judgment_raw = judgments[i] if i < len(judgments) else None
        judgment = judgment_raw if isinstance(judgment_raw, dict) else None
        transcript.append(
            TranscriptItem(
                index=i + 1,
                question=question,
                answer=answer,
                judgment=judgment,
            )
        )

    penalty = 0.0
    integrity_level = None
    low_identity_confidence = False
    identity_similarity_score = None
    if proctoring:
        penalty = float(proctoring.get("score_penalty_percent", 0.0))
        integrity_level = proctoring.get("integrity_level")
        low_identity_confidence = bool(proctoring.get("low_identity_confidence"))
        raw_similarity = proctoring.get("identity_similarity_score")
        if isinstance(raw_similarity, (int, float)):
            identity_similarity_score = float(raw_similarity)

    return RecruiterSessionDetail(
        session_id=row.session_id,
        candidate_name=_candidate_display_name(row.resume_filename),
        role_title=row.role_title,
        experience_level=row.experience_level,
        status=row.status,
        date=row.updated_at,
        created_at=row.created_at,
        duration_minutes=_duration_minutes(row),
        total_questions=int(row.total_questions or len(questions)),
        answered_count=len(answers),
        final_score=row.final_score,
        original_score=_extract_original_score(row.final_score),
        adjusted_score=_extract_adjusted_score(row.final_score),
        integrity_penalty_percent=penalty,
        integrity_level=integrity_level,
        proctoring_summary=proctoring,
        low_identity_confidence=low_identity_confidence,
        identity_similarity_score=identity_similarity_score,
        human_review_flag=_human_review_flag(row),
        recording_available=bool(row.recording_filename),
        recording_filename=row.recording_filename,
        transcript=transcript,
    )


class RecruiterService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_completed_sessions(self) -> list[RecruiterSessionSummary]:
        result = await self.db.execute(
            select(DBSession)
            .where(DBSession.status.in_(COMPLETED_STATUSES))
            .order_by(DBSession.updated_at.desc())
        )
        rows = result.scalars().all()
        return [_session_to_summary(row) for row in rows]

    async def get_session_detail(self, session_id: UUID) -> RecruiterSessionDetail:
        row = await self._get_completed_row(session_id)
        return _session_to_detail(row)

    async def get_session_report(self, session_id: UUID) -> tuple[bytes, str]:
        row = await self._get_completed_row(session_id)
        detail = _session_to_detail(row)
        pdf_bytes = generate_session_report_pdf(detail, row.proctoring_summary)
        return pdf_bytes, report_filename(detail)

    async def set_human_review_flag(self, session_id: UUID, flagged: bool) -> RecruiterSessionDetail:
        row = await self._get_completed_row(session_id)
        row.human_review_flag = flagged
        await self.db.commit()
        await self.db.refresh(row)
        return _session_to_detail(row)

    async def _get_completed_row(self, session_id: UUID) -> DBSession:
        row = await self.db.get(DBSession, session_id)
        if row is None or row.status not in COMPLETED_STATUSES:
            raise NotFoundException("Completed interview session not found")
        return row
