"""Recruiter queries over completed interview sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import String

from app.core.exceptions import InternalServerException, NotFoundException
from app.db.candidate_verification_model import CandidateVerification
from app.db.evidence_model import IdentityVerificationAttempt
from app.db.interview_invite_model import InterviewInvite
from app.db.session_model import Session as DBSession
from app.schemas.recruiter import (
    RecruiterIdentityVerificationMetadata,
    RecruiterProctorEvent,
    RecruiterReviewState,
    RecruiterSessionDetail,
    RecruiterSessionSummary,
    TranscriptItem,
)
from app.services.question_utils import question_text
from app.services.adaptive_interview import (
    adaptive_summary_for_recruiter,
    question_adaptive_meta,
)
from app.services.object_storage import get_object_storage


def _format_transcript_answer(answer: Any) -> str | None:
    """Expand coding JSON pointers into readable source for recruiter review."""
    if answer is None:
        return None
    if not isinstance(answer, str):
        return str(answer)
    text = answer.strip()
    if not text.startswith("{"):
        return answer
    try:
        import json

        payload = json.loads(text)
    except json.JSONDecodeError:
        return answer
    if not isinstance(payload, dict) or payload.get("kind") != "coding":
        return answer
    language = payload.get("language") or "unknown"
    key = payload.get("s3_key") or payload.get("storage_key")
    source = ""
    if key:
        try:
            source = get_object_storage().get_bytes(str(key)).decode("utf-8", errors="replace")
        except Exception:
            source = str(payload.get("preview") or "")
    else:
        source = str(payload.get("preview") or "")
    header = f"[{language}]\n"
    if len(source) > 8000:
        source = source[:8000] + "\n… (truncated)"
    return header + source
from app.services.report_service import generate_session_report_pdf, report_filename
from app.services.session_persistence import (
    get_session_review_state,
    list_proctor_events,
    upsert_session_artifact,
    upsert_session_review_state,
)

COMPLETED_STATUSES = ("completed", "ended")
REVIEW_STATUSES_REQUIRING_ATTENTION = {"needs_review", "in_review", "escalated"}


def _uuid_key(value: object) -> str:
    """Normalize UUID/hex forms for comparison (with or without hyphens)."""
    return str(value or "").replace("-", "").lower()


def _session_id_sql_key():
    """SQL expression: sessions.session_id as lowercase hex without hyphens."""
    return func.replace(func.lower(cast(DBSession.session_id, String)), "-", "")


def _verification_session_sql_key():
    return func.replace(func.lower(CandidateVerification.session_id), "-", "")


def _candidate_display_name(
    resume_filename: Optional[str],
    *,
    verification_name: Optional[str] = None,
    identity_name: Optional[str] = None,
) -> str:
    for candidate in (verification_name, identity_name):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    if not resume_filename or not resume_filename.strip():
        return "Unknown Candidate"
    stem = Path(resume_filename).stem
    if not stem:
        return "Unknown Candidate"
    return stem.replace("_", " ").replace("-", " ").strip().title()


def _as_score_dict(final_score: Any) -> dict[str, Any] | None:
    """Normalize final_score JSON; tolerate corrupt/partial session payloads."""
    if isinstance(final_score, dict):
        return final_score
    if isinstance(final_score, (int, float)):
        return {"final_score": float(final_score)}
    return None


def _extract_final_score(final_score: Any) -> tuple[Optional[float], Optional[str]]:
    payload = _as_score_dict(final_score)
    if not payload:
        return None, None
    score = payload.get("final_score")
    if score is None:
        score = payload.get("candidate_score")
    recommendation = payload.get("recommendation")
    if isinstance(score, (int, float)):
        return float(score), recommendation if isinstance(recommendation, str) else None
    return None, recommendation if isinstance(recommendation, str) else None


def _extract_original_score(final_score: Any) -> Optional[float]:
    payload = _as_score_dict(final_score)
    if not payload:
        return None
    raw = payload.get("original_score")
    if raw is None:
        raw = payload.get("final_score")
    if raw is None:
        raw = payload.get("candidate_score")
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _extract_adjusted_score(final_score: Any) -> Optional[float]:
    payload = _as_score_dict(final_score)
    if not payload:
        return None
    raw = payload.get("adjusted_final_score")
    if raw is None:
        raw = payload.get("final_score")
    if raw is None:
        raw = payload.get("candidate_score")
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


def _normalize_review_status(status: Optional[str]) -> str:
    value = str(status or "").strip().lower().replace("-", "_")
    return value or "pending"


def _human_review_required_for_status(status: str) -> bool:
    normalized = _normalize_review_status(status)
    return normalized in REVIEW_STATUSES_REQUIRING_ATTENTION


def _coerce_warnings(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _review_state_payload(row: DBSession) -> RecruiterReviewState:
    stored = get_session_review_state(row.session_id) or {}
    review_status = _normalize_review_status(
        stored.get("review_status")
        or ("needs_review" if _human_review_flag(row) else "pending")
    )
    return RecruiterReviewState(
        human_review_required=bool(
            stored.get("human_review_required", _human_review_required_for_status(review_status))
        ),
        review_status=review_status,
        review_notes=stored.get("review_notes"),
        reviewed_at=stored.get("reviewed_at"),
        reviewed_by_user_id=stored.get("reviewed_by_user_id"),
    )


def _identity_metadata_payload(
    attempt: IdentityVerificationAttempt | None,
    row: DBSession,
) -> RecruiterIdentityVerificationMetadata | None:
    if attempt is None:
        proctoring = row.proctoring_summary if isinstance(row.proctoring_summary, dict) else {}
        similarity = proctoring.get("identity_similarity_score")
        if not isinstance(similarity, (int, float)) and not proctoring.get("low_identity_confidence"):
            return None
        return RecruiterIdentityVerificationMetadata(
            low_identity_confidence=bool(proctoring.get("low_identity_confidence")),
            similarity_score=float(similarity) if isinstance(similarity, (int, float)) else None,
            liveness_confidence=(
                float(proctoring.get("identity_liveness_confidence"))
                if isinstance(proctoring.get("identity_liveness_confidence"), (int, float))
                else None
            ),
            ocr_name_match=(
                bool(proctoring.get("identity_ocr_name_match"))
                if isinstance(proctoring.get("identity_ocr_name_match"), bool)
                else None
            ),
        )

    metadata = attempt.evidence_metadata if isinstance(attempt.evidence_metadata, dict) else None
    return RecruiterIdentityVerificationMetadata(
        verified=bool(attempt.verified),
        confidence_score=(
            float(attempt.confidence_score)
            if isinstance(attempt.confidence_score, (int, float))
            else None
        ),
        low_identity_confidence=bool(attempt.low_identity_confidence),
        similarity_score=(
            float(attempt.similarity_score)
            if isinstance(attempt.similarity_score, (int, float))
            else None
        ),
        liveness_mode=attempt.liveness_mode,
        liveness_confidence=(
            float(attempt.liveness_confidence)
            if isinstance(attempt.liveness_confidence, (int, float))
            else None
        ),
        ocr_name=attempt.ocr_name,
        ocr_document_number=attempt.ocr_document_number,
        ocr_confidence=(
            float(attempt.ocr_confidence) if isinstance(attempt.ocr_confidence, (int, float)) else None
        ),
        ocr_name_match=metadata.get("ocr_name_match") if metadata else None,
        message=attempt.message,
        warnings=_coerce_warnings(metadata.get("warnings") if metadata else None),
        evidence_metadata=metadata,
        created_at=attempt.created_at,
    )


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


def _build_proctor_event_timeline(row: DBSession) -> list[RecruiterProctorEvent]:
    return [RecruiterProctorEvent(**event) for event in list_proctor_events(row.session_id)]


def _session_to_summary(
    row: DBSession,
    *,
    verification_name: Optional[str] = None,
) -> RecruiterSessionSummary:
    # invite_token is populated for Phase 4 filters/export; older clients ignore it.
    score, recommendation = _extract_final_score(row.final_score)
    review_state = _review_state_payload(row)
    proctoring = _build_proctoring_summary(row) or {}
    return RecruiterSessionSummary(
        session_id=row.session_id,
        candidate_name=_candidate_display_name(
            row.resume_filename,
            verification_name=verification_name,
        ),
        role_title=row.role_title,
        date=row.updated_at,
        final_score=score,
        recommendation=recommendation,
        status=row.status,
        recording_available=bool(row.recording_filename),
        human_review_flag=_human_review_flag(row),
        review_status=review_state.review_status,
        review_notes=review_state.review_notes,
        reviewed_at=review_state.reviewed_at,
        integrity_level=proctoring.get("integrity_level"),
        integrity_event_count=int(proctoring.get("total_violations", 0) or 0),
        low_identity_confidence=bool(proctoring.get("low_identity_confidence")),
        invite_token=getattr(row, "invite_token", None),
    )


def _session_to_detail(
    row: DBSession,
    identity_attempt: IdentityVerificationAttempt | None = None,
    *,
    verification_name: Optional[str] = None,
) -> RecruiterSessionDetail:
    questions = list(row.questions or [])
    answers = list(row.answers or [])
    judgments = list(row.answer_judgments or [])
    proctoring = _build_proctoring_summary(row)
    review_state = _review_state_payload(row)
    proctor_events = _build_proctor_event_timeline(row)
    identity_verification = _identity_metadata_payload(identity_attempt, row)

    transcript: list[TranscriptItem] = []
    for i, question in enumerate(questions):
        answer = answers[i] if i < len(answers) else None
        judgment_raw = judgments[i] if i < len(judgments) else None
        judgment = judgment_raw if isinstance(judgment_raw, dict) else None
        adaptive_meta = question_adaptive_meta(question)
        source = str(adaptive_meta.get("source") or "") or None
        display_answer = _format_transcript_answer(answer)
        transcript.append(
            TranscriptItem(
                index=i + 1,
                question=question_text(question),
                answer=display_answer,
                judgment=judgment,
                is_adaptive_follow_up=source == "adaptive_follow_up",
                adaptive_topic=adaptive_meta.get("topic"),
                adaptive_source=source,
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
        candidate_name=_candidate_display_name(
            row.resume_filename,
            verification_name=verification_name,
        ),
        role_title=row.role_title,
        experience_level=row.experience_level,
        status=row.status,
        date=row.updated_at,
        created_at=row.created_at,
        duration_minutes=_duration_minutes(row),
        total_questions=int(row.total_questions or len(questions)),
        answered_count=len(answers),
        final_score=_as_score_dict(row.final_score),
        original_score=_extract_original_score(row.final_score),
        adjusted_score=_extract_adjusted_score(row.final_score),
        integrity_penalty_percent=penalty,
        integrity_level=integrity_level,
        integrity_event_count=len(proctor_events),
        proctoring_summary=proctoring,
        low_identity_confidence=low_identity_confidence,
        identity_similarity_score=identity_similarity_score,
        human_review_flag=_human_review_flag(row),
        review_state=review_state,
        identity_verification=identity_verification,
        proctor_events=proctor_events,
        recording_available=bool(row.recording_filename),
        recording_filename=row.recording_filename,
        transcript=transcript,
        adaptive_interview=adaptive_summary_for_recruiter(
            getattr(row, "adaptive_state", None)
        ),
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
        rows = list(result.scalars().all())
        name_by_session = await self._candidate_names_for_sessions(
            [row.session_id for row in rows]
        )
        return [
            _session_to_summary(
                row,
                verification_name=name_by_session.get(_uuid_key(row.session_id)),
            )
            for row in rows
        ]

    async def get_session_detail(
        self, recruiter_id: int, session_id: UUID
    ) -> RecruiterSessionDetail:
        row = await self._get_owned_completed_row(recruiter_id, session_id)
        identity_attempt = await self._get_latest_identity_attempt(session_id)
        names = await self._candidate_names_for_sessions([session_id])
        return _session_to_detail(
            row,
            identity_attempt,
            verification_name=names.get(_uuid_key(session_id)),
        )

    async def get_session_report(
        self, recruiter_id: int, session_id: UUID
    ) -> tuple[bytes, str]:
        row = await self._get_owned_completed_row(recruiter_id, session_id)
        identity_attempt = await self._get_latest_identity_attempt(session_id)
        names = await self._candidate_names_for_sessions([session_id])
        try:
            detail = _session_to_detail(
                row,
                identity_attempt,
                verification_name=names.get(_uuid_key(session_id)),
            )
            pdf_bytes = generate_session_report_pdf(
                detail, _build_proctoring_summary(row)
            )
            if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
                raise ValueError("PDF generator returned empty or invalid output")
            filename = report_filename(detail)
        except NotFoundException:
            raise
        except Exception as exc:
            raise InternalServerException(
                "Failed to generate interview PDF report. "
                "The session may have incomplete data — try again or contact support."
            ) from exc
        try:
            upsert_session_artifact(
                artifact_type="recruiter_report_pdf",
                session_id=session_id,
                storage_path=None,
                mime_type="application/pdf",
                file_size_bytes=len(pdf_bytes),
                metadata_json={"filename": filename, "generated_on_demand": True},
            )
        except Exception:
            # Artifact index is best-effort; do not block the download.
            pass
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
        identity_attempt = await self._get_latest_identity_attempt(session_id)
        names = await self._candidate_names_for_sessions([session_id])
        return _session_to_detail(
            row,
            identity_attempt,
            verification_name=names.get(_uuid_key(session_id)),
        )

    async def update_review_state(
        self,
        recruiter_id: int,
        session_id: UUID,
        review_status: str,
        review_notes: str | None = None,
    ) -> RecruiterSessionDetail:
        row = await self._get_owned_completed_row(recruiter_id, session_id)
        normalized_status = _normalize_review_status(review_status)
        review_required = _human_review_required_for_status(normalized_status)
        row.human_review_flag = review_required
        await self.db.commit()
        upsert_session_review_state(
            session_id,
            human_review_required=review_required,
            review_status=normalized_status,
            review_notes=review_notes,
            reviewed_by_user_id=recruiter_id,
            reviewed_at=datetime.now(timezone.utc),
        )
        await self.db.refresh(row)
        identity_attempt = await self._get_latest_identity_attempt(session_id)
        names = await self._candidate_names_for_sessions([session_id])
        return _session_to_detail(
            row,
            identity_attempt,
            verification_name=names.get(_uuid_key(session_id)),
        )

    async def recruiter_owns_session(
        self, recruiter_id: int, session_id: UUID
    ) -> bool:
        """Return True if the session was started via this recruiter's invite."""
        row = await self.db.get(DBSession, session_id)
        if row is None:
            return False
        return await self._is_owned_by_recruiter(recruiter_id, row)

    async def _candidate_names_for_sessions(
        self, session_ids: list[UUID]
    ) -> dict[str, str]:
        """Map session_id hex-key -> registered candidate_name from invite verification."""
        if not session_ids:
            return {}
        keys = [_uuid_key(sid) for sid in session_ids]
        result = await self.db.execute(
            select(CandidateVerification).where(
                CandidateVerification.session_id.is_not(None),
                _verification_session_sql_key().in_(keys),
            )
        )
        out: dict[str, str] = {}
        for row in result.scalars().all():
            key = _uuid_key(row.session_id)
            name = (row.candidate_name or "").strip()
            if key and name and key not in out:
                out[key] = name
        return out

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

    async def _get_latest_identity_attempt(
        self, session_id: UUID
    ) -> IdentityVerificationAttempt | None:
        attempt = await self.db.execute(
            select(IdentityVerificationAttempt)
            .where(IdentityVerificationAttempt.session_id == str(session_id))
            .order_by(
                IdentityVerificationAttempt.created_at.desc(),
                IdentityVerificationAttempt.id.desc(),
            )
        )
        return attempt.scalars().first()
