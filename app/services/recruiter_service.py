"""Recruiter queries over completed interview sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import String

from app.core.exceptions import NotFoundException
from app.db.candidate_verification_model import CandidateVerification
from app.db.interview_invite_model import InterviewInvite
from app.db.session_model import Session as DBSession
from app.schemas.recruiter import RecruiterSessionDetail, RecruiterSessionSummary, TranscriptItem
from app.services.question_utils import question_text
from app.services.report_service import generate_session_report_pdf, report_filename
from app.services.session_persistence import (
    get_session_review_state,
    list_proctor_events,
    upsert_session_artifact,
    upsert_session_review_state,
)

COMPLETED_STATUSES = ("completed", "ended")


def _uuid_key(value: object) -> str:
    """Normalize UUID/hex forms for comparison (with or without hyphens)."""
    return str(value or "").replace("-", "").lower()


def _session_id_sql_key():
    """SQL expression: sessions.session_id as lowercase hex without hyphens."""
    return func.replace(func.lower(cast(DBSession.session_id, String)), "-", "")


def _verification_session_sql_key():
    return func.replace(func.lower(CandidateVerification.session_id), "-", "")


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
    review_state = get_session_review_state(row.session_id)
    if review_state is not None:
        return bool(review_state.get("human_review_required"))
    if bool(getattr(row, "human_review_flag", False)):
        return True
    proctoring = row.proctoring_summary if isinstance(row.proctoring_summary, dict) else {}
    if proctoring.get("low_identity_confidence"):
        return True
    level = proctoring.get("integrity_level")
    return level in ("moderate_concerns", "serious_concerns")


def _integrity_level_from_penalty(penalty: float) -> str:
    if penalty <= 0:
        return "clean"
    if penalty <= 10:
        return "minor_concerns"
    if penalty <= 25:
        return "moderate_concerns"
    return "serious_concerns"


def _build_proctoring_summary(row: DBSession) -> dict[str, Any] | None:
    summary = dict(row.proctoring_summary or {})
    events = list_proctor_events(row.session_id)
    if events:
        penalty = round(sum(float(e.get("penalty_percent", 0.0)) for e in events), 2)
        summary["violations"] = events
        summary["warnings"] = [
            {
                "level": idx + 1,
                "reason": event.get("message", ""),
                "timestamp": event.get("time"),
                "gaze": event.get("type"),
                "severity": event.get("severity"),
                "penalty_percent": event.get("penalty_percent", 0.0),
            }
            for idx, event in enumerate(events)
        ]
        summary["total_violations"] = len(events)
        summary["warning_count"] = len(events)
        summary["score_penalty_percent"] = penalty
        summary["integrity_level"] = _integrity_level_from_penalty(penalty)
        summary["terminated"] = False
    return summary or None


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
    proctoring = _build_proctoring_summary(row)

    transcript: list[TranscriptItem] = []
    for i, question in enumerate(questions):
        answer = answers[i] if i < len(answers) else None
        judgment_raw = judgments[i] if i < len(judgments) else None
        judgment = judgment_raw if isinstance(judgment_raw, dict) else None
        transcript.append(
            TranscriptItem(
                index=i + 1,
                question=question_text(question),
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

    async def list_completed_sessions(
        self, recruiter_id: int
    ) -> list[RecruiterSessionSummary]:
        """List completed sessions taken via this recruiter's invite links only."""
        owned_tokens = select(InterviewInvite.token).where(
            InterviewInvite.recruiter_id == recruiter_id
        )
        verification_session_keys = select(_verification_session_sql_key()).where(
            CandidateVerification.token.in_(owned_tokens),
            CandidateVerification.session_id.is_not(None),
        )
        result = await self.db.execute(
            select(DBSession)
            .where(
                DBSession.status.in_(COMPLETED_STATUSES),
                or_(
                    DBSession.invite_token.in_(owned_tokens),
                    _session_id_sql_key().in_(verification_session_keys),
                ),
            )
            .order_by(DBSession.updated_at.desc())
        )
        return [_session_to_summary(row) for row in result.scalars().all()]

    async def get_session_detail(
        self, recruiter_id: int, session_id: UUID
    ) -> RecruiterSessionDetail:
        row = await self._get_owned_completed_row(recruiter_id, session_id)
        return _session_to_detail(row)

    async def get_session_report(
        self, recruiter_id: int, session_id: UUID
    ) -> tuple[bytes, str]:
        row = await self._get_owned_completed_row(recruiter_id, session_id)
        detail = _session_to_detail(row)
        pdf_bytes = generate_session_report_pdf(detail, _build_proctoring_summary(row))
        filename = report_filename(detail)
        upsert_session_artifact(
            artifact_type="recruiter_report_pdf",
            session_id=session_id,
            storage_path=None,
            mime_type="application/pdf",
            file_size_bytes=len(pdf_bytes),
            metadata_json={"filename": filename, "generated_on_demand": True},
        )
        return pdf_bytes, filename

    async def set_human_review_flag(
        self, recruiter_id: int, session_id: UUID, flagged: bool
    ) -> RecruiterSessionDetail:
        row = await self._get_owned_completed_row(recruiter_id, session_id)
        row.human_review_flag = flagged
        await self.db.commit()
        upsert_session_review_state(
            session_id,
            human_review_required=flagged,
            review_status="needs_review" if flagged else "cleared",
            reviewed_by_user_id=recruiter_id,
        )
        await self.db.refresh(row)
        return _session_to_detail(row)

    async def recruiter_owns_session(
        self, recruiter_id: int, session_id: UUID
    ) -> bool:
        """Return True if the session was started via this recruiter's invite."""
        row = await self.db.get(DBSession, session_id)
        if row is None:
            return False
        return await self._is_owned_by_recruiter(recruiter_id, row)

    async def _get_owned_completed_row(
        self, recruiter_id: int, session_id: UUID
    ) -> DBSession:
        row = await self.db.get(DBSession, session_id)
        if row is None or row.status not in COMPLETED_STATUSES:
            raise NotFoundException("Completed interview session not found")
        if not await self._is_owned_by_recruiter(recruiter_id, row):
            # 404 avoids leaking that another tenant's session exists.
            raise NotFoundException("Completed interview session not found")
        return row

    async def _is_owned_by_recruiter(self, recruiter_id: int, row: DBSession) -> bool:
        token = getattr(row, "invite_token", None)
        if token:
            invite = await self.db.execute(
                select(InterviewInvite).where(InterviewInvite.token == token)
            )
            invite_row = invite.scalar_one_or_none()
            if invite_row is not None:
                return invite_row.recruiter_id == recruiter_id

        session_key = _uuid_key(row.session_id)
        verification = await self.db.execute(
            select(CandidateVerification, InterviewInvite)
            .join(
                InterviewInvite,
                InterviewInvite.token == CandidateVerification.token,
            )
            .where(
                _verification_session_sql_key() == session_key,
                InterviewInvite.recruiter_id == recruiter_id,
            )
        )
        return verification.first() is not None
