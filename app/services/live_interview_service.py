"""Live interview room service (demo MVP)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.db.job_live_models import LiveInterviewRoom
from app.services.coding_judge import LANGUAGE_STARTERS


DEFAULT_PROBLEM = """Two Sum (live demo)
Given an array of integers and a target, return two 0-based indices that sum to target.

Input:
  Line 1: N
  Line 2: N integers
  Line 3: target
Output: two indices i j

Example 1:
Input:
4
2 7 11 15
9
Output:
0 1
"""

DEFAULT_TESTS = [
    {"stdin": "4\n2 7 11 15\n9\n", "expected_stdout": "0 1"},
    {"stdin": "3\n3 2 4\n6\n", "expected_stdout": "1 2"},
]


class LiveInterviewService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_room(
        self,
        recruiter_id: int,
        *,
        title: str,
        meet_url: str | None = None,
        problem_text: str | None = None,
        language: str = "python",
        starter_code: str | None = None,
        public_tests: list[dict] | None = None,
        application_id: int | None = None,
        expiry_hours: int = 24,
    ) -> LiveInterviewRoom:
        title = (title or "").strip() or "Live technical interview"
        lang = (language or "python").strip().lower()
        if lang not in LANGUAGE_STARTERS:
            lang = "python"
        now = datetime.now(timezone.utc)
        room = LiveInterviewRoom(
            token=str(uuid.uuid4()),
            recruiter_id=recruiter_id,
            title=title[:255],
            meet_url=(meet_url or "").strip() or None,
            problem_text=(problem_text or DEFAULT_PROBLEM).strip(),
            starter_code=(starter_code or LANGUAGE_STARTERS.get(lang) or ""),
            language=lang,
            public_tests_json=public_tests or DEFAULT_TESTS,
            notes_json=[],
            status="open",
            application_id=application_id,
            expiry_at=now + timedelta(hours=max(1, min(expiry_hours, 168))),
            created_at=now,
        )
        self.db.add(room)
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def get_room(self, token: str) -> LiveInterviewRoom:
        result = await self.db.execute(
            select(LiveInterviewRoom).where(LiveInterviewRoom.token == token)
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise NotFoundException("Live room not found")
        now = datetime.now(timezone.utc)
        expiry = room.expiry_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if room.status == "ended" or expiry <= now:
            raise BadRequestException("This live interview link has expired or ended")
        return room

    async def list_rooms(self, recruiter_id: int) -> list[LiveInterviewRoom]:
        result = await self.db.execute(
            select(LiveInterviewRoom)
            .where(LiveInterviewRoom.recruiter_id == recruiter_id)
            .order_by(LiveInterviewRoom.created_at.desc())
            .limit(50)
        )
        return list(result.scalars().all())

    async def end_room(
        self,
        recruiter_id: int,
        token: str,
        *,
        final_code: str | None = None,
        notes: list | None = None,
    ) -> LiveInterviewRoom:
        result = await self.db.execute(
            select(LiveInterviewRoom).where(LiveInterviewRoom.token == token)
        )
        room = result.scalar_one_or_none()
        if room is None or room.recruiter_id != recruiter_id:
            raise NotFoundException("Live room not found")
        room.status = "ended"
        room.ended_at = datetime.now(timezone.utc)
        if final_code is not None:
            room.final_code = final_code
        if notes is not None:
            room.notes_json = notes
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def save_snapshot(
        self,
        token: str,
        *,
        code: str | None = None,
        language: str | None = None,
        notes: list | None = None,
    ) -> None:
        result = await self.db.execute(
            select(LiveInterviewRoom).where(LiveInterviewRoom.token == token)
        )
        room = result.scalar_one_or_none()
        if room is None or room.status != "open":
            return
        if code is not None:
            room.final_code = code
        if language:
            room.language = language
        if notes is not None:
            room.notes_json = notes
        await self.db.commit()
