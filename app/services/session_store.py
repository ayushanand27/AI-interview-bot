"""In-memory session cache with SQLite persistence via session_persistence."""

from typing import Optional
from uuid import UUID, uuid4

from app.models.session import InterviewSession
from app.services.session_persistence import (
    load_session_from_disk,
    save_session_to_disk,
)


class SessionStore:
    """Memory cache + disk persistence for interview sessions."""

    def __init__(self) -> None:
        self._sessions: dict[UUID, InterviewSession] = {}

    def create(
        self,
        *,
        user_id: int | None = None,
        role_title: str,
        experience_level: str,
        topic_focus: Optional[str],
        resume_filename: Optional[str] = None,
        resume_text: Optional[str] = None,
        job_description: Optional[str] = None,
    ) -> InterviewSession:
        session = InterviewSession(
            session_id=uuid4(),
            user_id=user_id,
            role_title=role_title,
            experience_level=experience_level,
            topic_focus=topic_focus,
            resume_filename=resume_filename,
            resume_text=resume_text,
            job_description=job_description,
        )
        self._sessions[session.session_id] = session
        save_session_to_disk(session)
        return session

    def get(self, session_id: UUID) -> Optional[InterviewSession]:
        if session_id in self._sessions:
            return self._sessions[session_id]

        session = load_session_from_disk(session_id)
        if session is not None:
            self._sessions[session_id] = session
        return session

    def save(self, session: InterviewSession) -> InterviewSession:
        self._sessions[session.session_id] = session
        save_session_to_disk(session)
        return session

    def delete(self, session_id: UUID) -> None:
        self._sessions.pop(session_id, None)


session_store = SessionStore()
