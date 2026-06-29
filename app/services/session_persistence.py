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

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import sessionmaker as sync_sessionmaker

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.session_model import Session as DBSess
from app.models.schemas import SessionStatus
from app.models.session import InterviewSession

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = PROJECT_ROOT / "data" / "sessions"

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)


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
    return PROJECT_ROOT / "smartskale.db"


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


async def _update_proctoring_summary_async(
    session_id: UUID, summary_dict: dict[str, Any]
) -> bool:
    """Update only proctoring_summary (and updated_at) for an existing session row."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(DBSess)
            .where(DBSess.session_id == session_id)
            .values(proctoring_summary=summary_dict, updated_at=now)
        )
        if result.rowcount == 0:
            return False
        await db.commit()
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
