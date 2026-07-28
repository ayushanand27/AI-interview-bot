"""Recruiter analytics: funnel, score/integrity distributions, assessment metrics."""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.candidate_verification_model import CandidateVerification
from app.db.interview_invite_model import InterviewInvite
from app.db.invite_funnel_model import InviteFunnelEvent
from app.db.session_model import Session as DBSession
from app.schemas.recruiter import (
    AssessmentPerformanceMetric,
    InviteFunnelMetrics,
    RecruiterAnalyticsResponse,
    RecruiterSessionFilters,
    RecruiterSessionSummary,
)
from app.services.question_utils import normalize_questions
from app.services.recruiter_service import (
    COMPLETED_STATUSES,
    _session_id_sql_key,
    _session_to_summary,
    _verification_session_sql_key,
)

SCORE_BANDS = ("Strong Hire", "Hire", "Maybe", "No Hire", "Unscored")
INTEGRITY_LEVELS = (
    "clean",
    "minor_concerns",
    "moderate_concerns",
    "serious_concerns",
    "unknown",
)


def _as_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _role_preview(jd_text: str) -> str:
    lines = (jd_text or "").strip().splitlines()
    return (lines[0][:80] if lines else "Assessment").strip() or "Assessment"


def _score_band(recommendation: str | None, score: float | None) -> str:
    if recommendation and recommendation in SCORE_BANDS[:-1]:
        return recommendation
    if score is None:
        return "Unscored"
    if score >= 85:
        return "Strong Hire"
    if score >= 70:
        return "Hire"
    if score >= 50:
        return "Maybe"
    return "No Hire"


def _matches_filters(
    summary: RecruiterSessionSummary,
    row: DBSession,
    filters: RecruiterSessionFilters | None,
) -> bool:
    if filters is None:
        return True

    if filters.role_title:
        needle = filters.role_title.strip().lower()
        if needle and needle not in (summary.role_title or "").lower():
            return False

    if filters.invite_token:
        token = (getattr(row, "invite_token", None) or "").strip()
        if token != filters.invite_token.strip():
            return False

    if filters.review_status:
        if summary.review_status != filters.review_status.strip().lower().replace("-", "_"):
            return False

    if filters.integrity_level:
        expected = filters.integrity_level.strip().lower()
        actual = (summary.integrity_level or "unknown").lower()
        if actual != expected:
            return False

    if filters.score_band:
        band = _score_band(summary.recommendation, summary.final_score)
        if band.lower() != filters.score_band.strip().lower():
            return False

    date_value = _as_aware_utc(summary.date)
    if filters.date_from and date_value:
        start = _as_aware_utc(filters.date_from)
        if start and date_value < start:
            return False
    if filters.date_to and date_value:
        end = _as_aware_utc(filters.date_to)
        if end and date_value > end:
            return False

    return True


class RecruiterAnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _owned_invites(self, recruiter_id: int) -> list[InterviewInvite]:
        result = await self.db.execute(
            select(InterviewInvite)
            .where(InterviewInvite.recruiter_id == recruiter_id)
            .order_by(InterviewInvite.created_at.desc())
        )
        return list(result.scalars().all())

    async def _owned_sessions(self, recruiter_id: int) -> list[DBSession]:
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
                or_(
                    DBSession.invite_token.in_(owned_tokens),
                    _session_id_sql_key().in_(verification_session_keys),
                ),
            )
            .order_by(DBSession.updated_at.desc())
        )
        return list(result.scalars().all())

    async def list_filtered_sessions(
        self,
        recruiter_id: int,
        filters: RecruiterSessionFilters | None = None,
    ) -> list[RecruiterSessionSummary]:
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
        out: list[RecruiterSessionSummary] = []
        for row in rows:
            summary = _session_to_summary(row)
            if _matches_filters(summary, row, filters):
                out.append(summary)
        return out

    async def get_analytics(
        self,
        recruiter_id: int,
        filters: RecruiterSessionFilters | None = None,
    ) -> RecruiterAnalyticsResponse:
        invites = await self._owned_invites(recruiter_id)
        tokens = [inv.token for inv in invites]
        all_sessions = await self._owned_sessions(recruiter_id)
        completed_rows = [
            row for row in all_sessions if row.status in COMPLETED_STATUSES
        ]
        completed_summaries: list[tuple[DBSession, RecruiterSessionSummary]] = []
        for row in completed_rows:
            summary = _session_to_summary(row)
            if _matches_filters(summary, row, filters):
                completed_summaries.append((row, summary))

        funnel = await self._build_funnel(tokens, invites, all_sessions)
        score_distribution = {band: 0 for band in SCORE_BANDS}
        integrity_distribution = {level: 0 for level in INTEGRITY_LEVELS}
        scores: list[float] = []
        integrity_flagged = 0
        review_flagged = 0

        for row, summary in completed_summaries:
            band = _score_band(summary.recommendation, summary.final_score)
            score_distribution[band] = score_distribution.get(band, 0) + 1
            if summary.final_score is not None:
                scores.append(float(summary.final_score))
            level = (summary.integrity_level or "unknown").lower()
            if level not in integrity_distribution:
                level = "unknown"
            integrity_distribution[level] = integrity_distribution.get(level, 0) + 1
            if level in ("moderate_concerns", "serious_concerns") or summary.human_review_flag:
                integrity_flagged += 1
            if summary.human_review_flag or summary.review_status in {
                "needs_review",
                "in_review",
                "escalated",
            }:
                review_flagged += 1

        completed_count = len(completed_summaries)
        registered_or_started = max(funnel.registered, funnel.started, 1)
        completion_rate = (
            round((completed_count / registered_or_started) * 100.0, 1)
            if funnel.registered or funnel.started
            else 0.0
        )
        avg_score = round(sum(scores) / len(scores), 1) if scores else None
        integrity_flag_rate = (
            round((integrity_flagged / completed_count) * 100.0, 1)
            if completed_count
            else 0.0
        )

        per_assessment = self._per_assessment_metrics(
            invites, all_sessions, completed_summaries
        )

        return RecruiterAnalyticsResponse(
            generated_at=datetime.now(timezone.utc),
            invite_count=len(invites),
            completed_session_count=completed_count,
            completion_rate_percent=completion_rate,
            average_score=avg_score,
            integrity_flag_rate_percent=integrity_flag_rate,
            review_flagged_count=review_flagged,
            funnel=funnel,
            score_distribution=score_distribution,
            integrity_distribution=integrity_distribution,
            assessments=per_assessment,
        )

    async def _build_funnel(
        self,
        tokens: list[str],
        invites: list[InterviewInvite],
        sessions: list[DBSession],
    ) -> InviteFunnelMetrics:
        created = len(invites)
        opened = 0
        registered = 0
        verified = 0
        started = 0
        completed = 0

        if tokens:
            events = await self.db.execute(
                select(InviteFunnelEvent).where(
                    InviteFunnelEvent.invite_token.in_(tokens)
                )
            )
            counts: Counter[str] = Counter()
            for event in events.scalars().all():
                counts[event.event_type] += 1
            opened = counts.get("opened", 0)
            registered = counts.get("registered", 0)
            verified = counts.get("verified", 0)
            started = counts.get("started", 0)
            completed = counts.get("completed", 0)

        # Fallback/derivation from existing tables when events are sparse (pre-Phase-4 data).
        if opened == 0:
            opened = sum(int(inv.used_count or 0) for inv in invites)
        if registered == 0 and tokens:
            ver_rows = await self.db.execute(
                select(CandidateVerification).where(
                    CandidateVerification.token.in_(tokens)
                )
            )
            verifications = list(ver_rows.scalars().all())
            registered = len(verifications)
            verified = sum(1 for v in verifications if v.verified)
        if started == 0:
            started = sum(
                1
                for row in sessions
                if row.status
                in (
                    "in_progress",
                    "completed",
                    "ended",
                )
            )
        if completed == 0:
            completed = sum(1 for row in sessions if row.status in COMPLETED_STATUSES)

        return InviteFunnelMetrics(
            created=created,
            opened=opened,
            registered=registered,
            verified=verified,
            started=started,
            completed=completed,
        )

    def _per_assessment_metrics(
        self,
        invites: list[InterviewInvite],
        all_sessions: list[DBSession],
        completed_summaries: list[tuple[DBSession, RecruiterSessionSummary]],
    ) -> list[AssessmentPerformanceMetric]:
        completed_by_token: dict[str, list[RecruiterSessionSummary]] = defaultdict(list)
        for row, summary in completed_summaries:
            token = getattr(row, "invite_token", None) or ""
            if token:
                completed_by_token[token].append(summary)

        started_by_token: Counter[str] = Counter()
        for row in all_sessions:
            token = getattr(row, "invite_token", None) or ""
            if token and row.status in ("in_progress", "completed", "ended"):
                started_by_token[token] += 1

        metrics: list[AssessmentPerformanceMetric] = []
        for invite in invites:
            completed_list = completed_by_token.get(invite.token, [])
            scores = [
                float(s.final_score)
                for s in completed_list
                if s.final_score is not None
            ]
            flagged = sum(
                1
                for s in completed_list
                if s.human_review_flag
                or (s.integrity_level or "")
                in ("moderate_concerns", "serious_concerns")
            )
            questions = normalize_questions(list(invite.questions_json or []))
            metrics.append(
                AssessmentPerformanceMetric(
                    token=invite.token,
                    role_preview=_role_preview(invite.jd_text),
                    difficulty=invite.difficulty,
                    question_count=len(questions),
                    used_count=int(invite.used_count or 0),
                    started_count=started_by_token.get(invite.token, 0),
                    completed_count=len(completed_list),
                    average_score=round(sum(scores) / len(scores), 1) if scores else None,
                    integrity_flag_count=flagged,
                    created_at=_as_aware_utc(invite.created_at) or datetime.now(timezone.utc),
                )
            )
        return metrics

    async def export_sessions_csv(
        self,
        recruiter_id: int,
        filters: RecruiterSessionFilters | None = None,
    ) -> tuple[str, str]:
        sessions = await self.list_filtered_sessions(recruiter_id, filters)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "session_id",
                "candidate_name",
                "role_title",
                "date",
                "final_score",
                "recommendation",
                "review_status",
                "integrity_level",
                "integrity_event_count",
                "human_review_flag",
                "low_identity_confidence",
                "invite_token",
                "status",
            ]
        )
        for row in sessions:
            writer.writerow(
                [
                    str(row.session_id),
                    row.candidate_name,
                    row.role_title,
                    row.date.isoformat() if row.date else "",
                    "" if row.final_score is None else f"{row.final_score:.2f}",
                    row.recommendation or "",
                    row.review_status,
                    row.integrity_level or "",
                    row.integrity_event_count,
                    "yes" if row.human_review_flag else "no",
                    "yes" if row.low_identity_confidence else "no",
                    getattr(row, "invite_token", None) or "",
                    row.status,
                ]
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        return buffer.getvalue(), f"recruiter-sessions-{stamp}.csv"

    async def export_assessments_csv(self, recruiter_id: int) -> tuple[str, str]:
        analytics = await self.get_analytics(recruiter_id)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "token",
                "role_preview",
                "difficulty",
                "question_count",
                "used_count",
                "started_count",
                "completed_count",
                "average_score",
                "integrity_flag_count",
                "created_at",
            ]
        )
        for item in analytics.assessments:
            writer.writerow(
                [
                    item.token,
                    item.role_preview,
                    item.difficulty,
                    item.question_count,
                    item.used_count,
                    item.started_count,
                    item.completed_count,
                    "" if item.average_score is None else f"{item.average_score:.1f}",
                    item.integrity_flag_count,
                    item.created_at.isoformat() if item.created_at else "",
                ]
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        return buffer.getvalue(), f"recruiter-assessments-{stamp}.csv"
