"""Session persistence backed by the SQLite `sessions` table (SQLAlchemy async).

Keeps the same function signatures used by `SessionStore` so callers stay unchanged.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.orm import sessionmaker as sync_sessionmaker

from app.core.config import settings
from app.db.evidence_model import (
    IdentityVerificationAttempt,
    ProctorEvent,
    SessionArtifact,
    SessionReviewState,
)
from app.db.session import AsyncSessionLocal
from app.db.session_model import Session as DBSess
from app.models.schemas import SessionStatus
from app.models.session import InterviewSession

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = PROJECT_ROOT / "data" / "sessions"

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _ensure_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return _utc_now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _timestamp_to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError):
            return _utc_now()
    return _utc_now()


def _review_status_for_flag(flagged: bool) -> str:
    return "needs_review" if flagged else "cleared"


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    return url


@lru_cache
def _get_sync_session_local():
    engine = create_engine(_sync_database_url(), pool_pre_ping=True)
    return sync_sessionmaker(bind=engine, expire_on_commit=False)


def _save_session_sync(session: InterviewSession) -> None:
    now = datetime.now(timezone.utc)
    SessionLocal = _get_sync_session_local()
    with SessionLocal() as db:
        obj = db.get(DBSess, session.session_id)
        if obj is None:
            db.add(_interview_session_to_row(session, now))
        else:
            _apply_session_fields(obj, session, now)
        db.commit()


def _load_session_sync(session_id: UUID) -> Optional[InterviewSession]:
    SessionLocal = _get_sync_session_local()
    with SessionLocal() as db:
        obj = db.get(DBSess, session_id)
        if obj is not None:
            return _row_to_interview_session(obj)
    return None


def _run_async(coro):
    """Run an async coroutine from sync code (including inside FastAPI's event loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return _executor.submit(asyncio.run, coro).result()


def ensure_sessions_dir() -> Path:
    """Legacy helper — only used when falling back to JSON session files."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


def _session_file_path(session_id: UUID) -> Path:
    return ensure_sessions_dir() / f"{session_id}.json"


def _build_qa_pairs(session: InterviewSession) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for i, question in enumerate(session.questions):
        answer = session.answers[i] if i < len(session.answers) else None
        pairs.append({"index": i, "question": question, "answer": answer})
    return pairs


def session_to_dict(session: InterviewSession, updated_at: datetime) -> dict[str, Any]:
    return {
        "session_id": str(session.session_id),
        "role_title": session.role_title,
        "experience_level": session.experience_level,
        "topic_focus": session.topic_focus,
        "resume_filename": session.resume_filename,
        "resume_text": session.resume_text,
        "job_description": session.job_description,
        "status": session.status.value,
        "questions": session.questions,
        "answers": session.answers,
        "answer_judgments": session.answer_judgments,
        "qa_pairs": _build_qa_pairs(session),
        "current_question_index": session.current_question_index,
        "total_questions": session.total_questions,
        "answered_count": len(session.answers),
        "created_at": session.created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }


def _row_to_interview_session(obj: DBSess) -> InterviewSession:
    return InterviewSession(
        session_id=obj.session_id,
        user_id=obj.user_id,
        role_title=obj.role_title,
        experience_level=obj.experience_level,
        topic_focus=obj.topic_focus,
        resume_filename=obj.resume_filename,
        resume_text=obj.resume_text,
        job_description=obj.job_description,
        status=SessionStatus(obj.status),
        questions=list(obj.questions or []),
        answers=list(obj.answers or []),
        answer_judgments=list(obj.answer_judgments or []),
        final_score=obj.final_score,
        proctoring_summary=obj.proctoring_summary,
        invite_token=getattr(obj, "invite_token", None),
        current_question_index=int(obj.current_question_index or 0),
        created_at=obj.created_at,
    )


def _interview_session_to_row(session: InterviewSession, now: datetime) -> DBSess:
    return DBSess(
        session_id=session.session_id,
        user_id=session.user_id,
        role_title=session.role_title,
        experience_level=session.experience_level,
        topic_focus=session.topic_focus,
        resume_filename=session.resume_filename,
        resume_text=session.resume_text,
        job_description=session.job_description,
        status=session.status.value,
        questions=session.questions,
        answers=session.answers,
        answer_judgments=session.answer_judgments,
        final_score=session.final_score,
        proctoring_summary=session.proctoring_summary,
        invite_token=getattr(session, "invite_token", None),
        current_question_index=session.current_question_index,
        total_questions=session.total_questions,
        created_at=session.created_at,
        updated_at=now,
    )


def _apply_session_fields(obj: DBSess, session: InterviewSession, now: datetime) -> None:
    obj.user_id = session.user_id
    obj.role_title = session.role_title
    obj.experience_level = session.experience_level
    obj.topic_focus = session.topic_focus
    obj.resume_filename = session.resume_filename
    obj.resume_text = session.resume_text
    obj.job_description = session.job_description
    obj.status = session.status.value
    obj.questions = session.questions
    obj.answers = session.answers
    obj.answer_judgments = session.answer_judgments
    obj.final_score = session.final_score
    obj.proctoring_summary = session.proctoring_summary
    # Preserve invite linkage; never blank an existing token on partial domain updates.
    session_invite = getattr(session, "invite_token", None)
    if session_invite:
        obj.invite_token = session_invite
    obj.current_question_index = session.current_question_index
    obj.total_questions = session.total_questions
    obj.updated_at = now


async def _save_session_async(session: InterviewSession) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        obj = await db.get(DBSess, session.session_id)
        if obj is None:
            db.add(_interview_session_to_row(session, now))
        else:
            _apply_session_fields(obj, session, now)
        await db.commit()


async def _load_session_async(session_id: UUID) -> Optional[InterviewSession]:
    async with AsyncSessionLocal() as db:
        obj = await db.get(DBSess, session_id)
        if obj is not None:
            return _row_to_interview_session(obj)
    return None


async def _list_session_ids_async() -> list[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(DBSess.session_id))
        return sorted(str(row[0]) for row in result.all())


def _load_session_from_json(session_id: UUID) -> Optional[InterviewSession]:
    """One-time fallback for sessions created before the DB migration."""
    path = _session_file_path(session_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    created_at = datetime.fromisoformat(data["created_at"])
    return InterviewSession(
        session_id=UUID(data["session_id"]),
        user_id=data.get("user_id"),
        role_title=data["role_title"],
        experience_level=data["experience_level"],
        topic_focus=data.get("topic_focus"),
        resume_filename=data.get("resume_filename"),
        resume_text=data.get("resume_text"),
        job_description=data.get("job_description"),
        status=SessionStatus(data["status"]),
        questions=list(data.get("questions", [])),
        answers=list(data.get("answers", [])),
        answer_judgments=list(data.get("answer_judgments", [])),
        current_question_index=int(data.get("current_question_index", 0)),
        created_at=created_at,
    )


def save_session_to_disk(session: InterviewSession) -> Path:
    """Persist session to the database."""
    _save_session_sync(session)
    return PROJECT_ROOT / "interview_bot.db"


def load_session_from_disk(session_id: UUID) -> Optional[InterviewSession]:
    """Load session from the database (JSON files used only as legacy fallback)."""
    loaded = _load_session_sync(session_id)
    if loaded is not None:
        return loaded
    legacy = _load_session_from_json(session_id)
    if legacy is not None:
        _save_session_sync(legacy)
    return legacy


def list_saved_session_ids() -> list[str]:
    return _run_async(_list_session_ids_async())


async def _replace_proctor_events_async(
    session_id: UUID, summary_dict: dict[str, Any]
) -> list[dict[str, Any]]:
    warnings = summary_dict.get("violations") or summary_dict.get("warnings") or []
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ProctorEvent).where(ProctorEvent.session_id == session_id))

        created: list[dict[str, Any]] = []
        now = _utc_now()
        for idx, item in enumerate(warnings):
            if not isinstance(item, dict):
                continue
            event_type = str(item.get("type") or item.get("gaze") or "unknown")
            severity = str(item.get("severity") or item.get("level") or "minor")
            timestamp = item.get("time", item.get("timestamp"))
            event_dt = _timestamp_to_datetime(timestamp)
            message = str(item.get("message") or item.get("reason") or event_type)
            penalty = item.get("penalty_percent", 0.0)
            try:
                penalty_value = float(penalty)
            except (TypeError, ValueError):
                penalty_value = 0.0

            metadata = {
                "source": "summary_backfill",
                "ordinal": idx,
            }
            for key in ("gaze", "level", "reason"):
                if item.get(key) is not None:
                    metadata[key] = item.get(key)

            db.add(
                ProctorEvent(
                    session_id=session_id,
                    event_type=event_type,
                    severity=severity,
                    message=message,
                    penalty_percent=penalty_value,
                    event_timestamp=event_dt,
                    evidence_metadata=metadata,
                    created_at=now,
                )
            )
            created.append(
                {
                    "type": event_type,
                    "severity": severity,
                    "time": event_dt.timestamp(),
                    "penalty_percent": penalty_value,
                    "message": message,
                }
            )

        await db.commit()
        return created


async def _list_proctor_events_async(session_id: UUID) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProctorEvent)
            .where(ProctorEvent.session_id == session_id)
            .order_by(ProctorEvent.event_timestamp.asc(), ProctorEvent.id.asc())
        )
        rows = result.scalars().all()
        return [
            {
                "type": row.event_type,
                "severity": row.severity,
                "time": _ensure_utc(row.event_timestamp).timestamp(),
                "penalty_percent": float(row.penalty_percent or 0.0),
                "message": row.message,
                "evidence_metadata": row.evidence_metadata or None,
            }
            for row in rows
        ]


def list_proctor_events(session_id: UUID | str) -> list[dict[str, Any]]:
    session_uuid = _coerce_uuid(session_id)
    if session_uuid is None:
        return []
    return _run_async(_list_proctor_events_async(session_uuid))


async def _upsert_session_artifact_async(
    *,
    artifact_type: str,
    session_id: UUID | None = None,
    candidate_verification_id: int | None = None,
    storage_path: str | None = None,
    mime_type: str | None = None,
    file_size_bytes: int | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> int:
    now = _utc_now()
    async with AsyncSessionLocal() as db:
        query = select(SessionArtifact).where(
            SessionArtifact.artifact_type == artifact_type,
            SessionArtifact.session_id == session_id,
            SessionArtifact.candidate_verification_id == candidate_verification_id,
            SessionArtifact.storage_path == storage_path,
        )
        existing = (await db.execute(query)).scalar_one_or_none()
        if existing is None:
            existing = SessionArtifact(
                artifact_type=artifact_type,
                session_id=session_id,
                candidate_verification_id=candidate_verification_id,
                storage_path=storage_path,
                mime_type=mime_type,
                file_size_bytes=file_size_bytes,
                metadata_json=metadata_json,
                created_at=now,
            )
            db.add(existing)
        else:
            existing.mime_type = mime_type
            existing.file_size_bytes = file_size_bytes
            existing.metadata_json = metadata_json
        await db.commit()
        await db.refresh(existing)
        return int(existing.id)


def upsert_session_artifact(
    *,
    artifact_type: str,
    session_id: UUID | str | None = None,
    candidate_verification_id: int | None = None,
    storage_path: str | None = None,
    mime_type: str | None = None,
    file_size_bytes: int | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> int:
    return int(
        _run_async(
            _upsert_session_artifact_async(
                artifact_type=artifact_type,
                session_id=_coerce_uuid(session_id),
                candidate_verification_id=candidate_verification_id,
                storage_path=storage_path,
                mime_type=mime_type,
                file_size_bytes=file_size_bytes,
                metadata_json=metadata_json,
            )
        )
    )


async def _list_session_artifacts_async(
    *,
    session_id: UUID | None = None,
    candidate_verification_id: int | None = None,
    artifact_type: str | None = None,
) -> list[SessionArtifact]:
    async with AsyncSessionLocal() as db:
        query = select(SessionArtifact)
        if session_id is not None:
            query = query.where(SessionArtifact.session_id == session_id)
        if candidate_verification_id is not None:
            query = query.where(
                SessionArtifact.candidate_verification_id == candidate_verification_id
            )
        if artifact_type is not None:
            query = query.where(SessionArtifact.artifact_type == artifact_type)
        query = query.order_by(SessionArtifact.created_at.desc(), SessionArtifact.id.desc())
        result = await db.execute(query)
        return list(result.scalars().all())


def list_session_artifacts(
    *,
    session_id: UUID | str | None = None,
    candidate_verification_id: int | None = None,
    artifact_type: str | None = None,
) -> list[SessionArtifact]:
    return _run_async(
        _list_session_artifacts_async(
            session_id=_coerce_uuid(session_id),
            candidate_verification_id=candidate_verification_id,
            artifact_type=artifact_type,
        )
    )


async def _upsert_session_review_state_async(
    session_id: UUID,
    *,
    human_review_required: bool,
    review_status: str | None = None,
    review_notes: str | None = None,
    reviewed_by_user_id: int | None = None,
    reviewed_at: datetime | None = None,
) -> bool:
    now = _utc_now()
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(
                select(SessionReviewState).where(SessionReviewState.session_id == session_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = SessionReviewState(
                session_id=session_id,
                human_review_required=human_review_required,
                review_status=review_status or _review_status_for_flag(human_review_required),
                review_notes=review_notes,
                reviewed_at=_ensure_utc(reviewed_at) if reviewed_at else None,
                reviewed_by_user_id=reviewed_by_user_id,
                created_at=now,
                updated_at=now,
            )
            db.add(existing)
        else:
            existing.human_review_required = human_review_required
            existing.review_status = review_status or _review_status_for_flag(
                human_review_required
            )
            if review_notes is not None:
                existing.review_notes = review_notes
            existing.reviewed_at = _ensure_utc(reviewed_at) if reviewed_at else None
            existing.reviewed_by_user_id = reviewed_by_user_id
            existing.updated_at = now
        await db.commit()
        return True


def upsert_session_review_state(
    session_id: UUID | str,
    *,
    human_review_required: bool,
    review_status: str | None = None,
    review_notes: str | None = None,
    reviewed_by_user_id: int | None = None,
    reviewed_at: datetime | None = None,
) -> bool:
    session_uuid = _coerce_uuid(session_id)
    if session_uuid is None:
        return False
    return bool(
        _run_async(
            _upsert_session_review_state_async(
                session_uuid,
                human_review_required=human_review_required,
                review_status=review_status,
                review_notes=review_notes,
                reviewed_by_user_id=reviewed_by_user_id,
                reviewed_at=reviewed_at,
            )
        )
    )


async def _get_session_review_state_async(session_id: UUID) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(
                select(SessionReviewState).where(SessionReviewState.session_id == session_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            return None
        return {
            "human_review_required": bool(existing.human_review_required),
            "review_status": existing.review_status,
            "review_notes": existing.review_notes,
            "reviewed_at": existing.reviewed_at,
            "reviewed_by_user_id": existing.reviewed_by_user_id,
        }


def get_session_review_state(session_id: UUID | str) -> dict[str, Any] | None:
    session_uuid = _coerce_uuid(session_id)
    if session_uuid is None:
        return None
    return _run_async(_get_session_review_state_async(session_uuid))


async def _record_identity_verification_attempt_async(
    *,
    candidate_verification_id: int,
    token: str,
    session_id: str | None,
    verified: bool,
    confidence_score: float | None,
    low_identity_confidence: bool,
    similarity_score: float | None,
    message: str,
    id_artifact_id: int | None,
    selfie_artifact_id: int | None,
) -> int:
    now = _utc_now()
    async with AsyncSessionLocal() as db:
        attempt = IdentityVerificationAttempt(
            candidate_verification_id=candidate_verification_id,
            token=token,
            session_id=session_id,
            verified=verified,
            confidence_score=confidence_score,
            low_identity_confidence=low_identity_confidence,
            similarity_score=similarity_score,
            message=message,
            id_artifact_id=id_artifact_id,
            selfie_artifact_id=selfie_artifact_id,
            created_at=now,
        )
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)
        return int(attempt.id)


def record_identity_verification_attempt(
    *,
    candidate_verification_id: int,
    token: str,
    session_id: str | None,
    verified: bool,
    confidence_score: float | None,
    low_identity_confidence: bool,
    similarity_score: float | None,
    message: str,
    id_artifact_id: int | None,
    selfie_artifact_id: int | None,
) -> int:
    return int(
        _run_async(
            _record_identity_verification_attempt_async(
                candidate_verification_id=candidate_verification_id,
                token=token,
                session_id=session_id,
                verified=verified,
                confidence_score=confidence_score,
                low_identity_confidence=low_identity_confidence,
                similarity_score=similarity_score,
                message=message,
                id_artifact_id=id_artifact_id,
                selfie_artifact_id=selfie_artifact_id,
            )
        )
    )


async def _update_proctoring_summary_async(
    session_id: UUID, summary_dict: dict[str, Any]
) -> bool:
    """Update only proctoring_summary (and updated_at) for an existing session row."""
    now = _utc_now()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(DBSess)
            .where(DBSess.session_id == session_id)
            .values(proctoring_summary=summary_dict, updated_at=now)
        )
        if result.rowcount == 0:
            return False
        await db.commit()
    await _replace_proctor_events_async(session_id, summary_dict)
    return True


def update_proctoring_summary(session_id: UUID | str, summary_dict: dict[str, Any]) -> bool:
    """
    Persist proctoring summary for one interview session.

    Updates only the proctoring_summary column (plus updated_at).
    Returns True if a row was updated, False if session_id is invalid or not found.
    """
    if isinstance(session_id, str):
        try:
            session_id = UUID(session_id)
        except ValueError:
            return False
    return bool(_run_async(_update_proctoring_summary_async(session_id, summary_dict)))


async def _update_recording_filename_async(
    session_id: UUID, filename: str
) -> bool:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(DBSess)
            .where(DBSess.session_id == session_id)
            .values(recording_filename=filename, updated_at=now)
        )
        if result.rowcount == 0:
            return False
        await db.commit()
        return True


def update_recording_filename(session_id: UUID | str, filename: str) -> bool:
    if isinstance(session_id, str):
        try:
            session_id = UUID(session_id)
        except ValueError:
            return False
    return bool(_run_async(_update_recording_filename_async(session_id, filename)))


async def _get_recording_filename_async(session_id: UUID) -> Optional[str]:
    async with AsyncSessionLocal() as db:
        obj = await db.get(DBSess, session_id)
        if obj is None:
            return None
        return obj.recording_filename


async def _update_recording_mp4_filename_async(
    session_id: UUID, filename: str
) -> bool:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(DBSess)
            .where(DBSess.session_id == session_id)
            .values(recording_mp4_filename=filename, updated_at=now)
        )
        if result.rowcount == 0:
            return False
        await db.commit()
        return True


def update_recording_mp4_filename(session_id: UUID | str, filename: str) -> bool:
    if isinstance(session_id, str):
        try:
            session_id = UUID(session_id)
        except ValueError:
            return False
    return bool(_run_async(_update_recording_mp4_filename_async(session_id, filename)))


async def _get_recording_mp4_filename_async(session_id: UUID) -> Optional[str]:
    async with AsyncSessionLocal() as db:
        obj = await db.get(DBSess, session_id)
        if obj is None:
            return None
        return obj.recording_mp4_filename


async def check_database_connected_async() -> bool:
    """Return True if the database accepts a simple query."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
            return True
    except Exception:
        return False


async def count_sessions_async() -> int:
    """Return total rows in the sessions table."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.count()).select_from(DBSess))
        return int(result.scalar_one())


ACTIVE_SESSION_STATUSES = ("created", "questions_ready", "in_progress")


async def _find_active_session_async(user_id: int) -> Optional[UUID]:
    """Return the most recent active session for a user, if any."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DBSess.session_id)
            .where(
                DBSess.user_id == user_id,
                DBSess.status.in_(ACTIVE_SESSION_STATUSES),
            )
            .order_by(DBSess.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


def find_active_session_for_user(user_id: int) -> Optional[UUID]:
    return _run_async(_find_active_session_async(user_id))


async def _abandon_active_sessions_async(user_id: int) -> list[UUID]:
    """Mark all in-flight sessions for a user as abandoned."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DBSess).where(
                DBSess.user_id == user_id,
                DBSess.status.in_(ACTIVE_SESSION_STATUSES),
            )
        )
        stale_sessions = result.scalars().all()
        abandoned_ids = [s.session_id for s in stale_sessions]
        for row in stale_sessions:
            row.status = SessionStatus.ABANDONED.value
            row.updated_at = now
        await db.commit()
        return abandoned_ids


def mark_candidate_report_email_sent(session_id: UUID) -> bool:
    """Record that the candidate report email was sent for this session."""
    return bool(_run_async(_mark_candidate_report_email_sent_async(session_id)))


async def _candidate_report_email_sent_async(session_id: UUID) -> bool:
    async with AsyncSessionLocal() as db:
        obj = await db.get(DBSess, session_id)
        return obj is not None and obj.candidate_report_email_sent_at is not None


def candidate_report_email_already_sent(session_id: UUID) -> bool:
    """Return True if the candidate report email was already sent."""
    return bool(_run_async(_candidate_report_email_sent_async(session_id)))


async def _mark_candidate_report_email_sent_async(session_id: UUID) -> bool:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(DBSess)
            .where(
                DBSess.session_id == session_id,
                DBSess.candidate_report_email_sent_at.is_(None),
            )
            .values(candidate_report_email_sent_at=now, updated_at=now)
        )
        if result.rowcount == 0:
            return False
        await db.commit()
        return True


async def abandon_active_sessions_for_user_async(user_id: int) -> int:
    """Abandon stale sessions in DB and sync the in-memory session cache (async-safe)."""
    from app.services.session_store import session_store

    abandoned_ids = await _abandon_active_sessions_async(user_id)
    for session_id in abandoned_ids:
        session = session_store.get(session_id)
        if session is not None:
            session.status = SessionStatus.ABANDONED
            session_store.save(session)
    return len(abandoned_ids)


def abandon_active_sessions_for_user(user_id: int) -> int:
    """Abandon stale sessions in DB and sync the in-memory session cache."""
    from app.services.session_store import session_store

    abandoned_ids = _run_async(_abandon_active_sessions_async(user_id))
    for session_id in abandoned_ids:
        session = session_store.get(session_id)
        if session is not None:
            session.status = SessionStatus.ABANDONED
            session_store.save(session)
    return len(abandoned_ids)


def set_human_review_flag(session_id: UUID, flagged: bool = True) -> bool:
    """Set human review flag on a persisted session (sync-safe)."""
    SessionLocal = _get_sync_session_local()
    with SessionLocal() as db:
        obj = db.get(DBSess, session_id)
        if obj is None:
            return False
        obj.human_review_flag = flagged
        now = _utc_now()
        review = db.execute(
            select(SessionReviewState).where(SessionReviewState.session_id == session_id)
        )
        review = review.scalar_one_or_none()
        if review is None:
            review = SessionReviewState(
                session_id=session_id,
                human_review_required=flagged,
                review_status=_review_status_for_flag(flagged),
                created_at=now,
                updated_at=now,
            )
            db.add(review)
        else:
            review.human_review_required = flagged
            review.review_status = _review_status_for_flag(flagged)
            review.updated_at = now
        db.commit()
        return True
