"""Lightweight invite funnel event recording for recruiter analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from uuid import UUID

from sqlalchemy import and_, create_engine, select
from sqlalchemy.orm import sessionmaker as sync_sessionmaker

from app.core.config import settings
from app.db.invite_funnel_model import InviteFunnelEvent

FUNNEL_EVENT_TYPES = (
    "created",
    "opened",
    "registered",
    "verified",
    "started",
    "completed",
)

# Avoid flooding analytics when candidates refresh the invite landing page.
_OPENED_DEDUPE_MINUTES = 30


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql", 1)
    return url


@lru_cache(maxsize=1)
def _get_sync_session_local():
    engine = create_engine(_sync_database_url(), pool_pre_ping=True)
    return sync_sessionmaker(bind=engine, expire_on_commit=False)


def record_invite_funnel_event(
    *,
    invite_token: str,
    event_type: str,
    session_id: UUID | str | None = None,
    candidate_email: str | None = None,
    metadata: dict[str, Any] | None = None,
    dedupe_opened: bool = True,
) -> None:
    """Persist a funnel event. Failures are swallowed so product flows never break."""
    token = (invite_token or "").strip()
    event = (event_type or "").strip().lower()
    if not token or event not in FUNNEL_EVENT_TYPES:
        return

    session_key = str(session_id) if session_id is not None else None
    email = (candidate_email or "").strip().lower() or None
    now = datetime.now(timezone.utc)

    try:
        SessionLocal = _get_sync_session_local()
        with SessionLocal() as db:
            if event == "opened" and dedupe_opened:
                cutoff = now - timedelta(minutes=_OPENED_DEDUPE_MINUTES)
                recent = db.execute(
                    select(InviteFunnelEvent.id)
                    .where(
                        and_(
                            InviteFunnelEvent.invite_token == token,
                            InviteFunnelEvent.event_type == "opened",
                            InviteFunnelEvent.created_at >= cutoff,
                        )
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if recent is not None:
                    return

            if (
                event in ("registered", "verified", "started", "completed")
                and session_key
            ):
                existing = db.execute(
                    select(InviteFunnelEvent.id)
                    .where(
                        and_(
                            InviteFunnelEvent.invite_token == token,
                            InviteFunnelEvent.event_type == event,
                            InviteFunnelEvent.session_id == session_key,
                        )
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if existing is not None:
                    return

            db.add(
                InviteFunnelEvent(
                    invite_token=token,
                    event_type=event,
                    session_id=session_key,
                    candidate_email=email,
                    metadata_json=metadata,
                    created_at=now,
                )
            )
            db.commit()
    except Exception:
        pass
