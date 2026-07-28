from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.recruiter import RecruiterSessionFilters, RecruiterSessionSummary
from app.services import recruiter_analytics_service as analytics_module
from app.services.recruiter_analytics_service import (
    RecruiterAnalyticsService,
    _matches_filters,
    _score_band,
)


def _summary(**kwargs) -> RecruiterSessionSummary:
    defaults = dict(
        session_id=uuid4(),
        candidate_name="Jane Doe",
        role_title="Backend Engineer",
        date=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
        final_score=82.0,
        recommendation="Hire",
        status="completed",
        recording_available=True,
        human_review_flag=False,
        review_status="cleared",
        review_notes=None,
        reviewed_at=None,
        integrity_level="clean",
        integrity_event_count=0,
        low_identity_confidence=False,
        invite_token="token-a",
    )
    defaults.update(kwargs)
    return RecruiterSessionSummary(**defaults)


def _row(**kwargs):
    return SimpleNamespace(
        session_id=kwargs.get("session_id", uuid4()),
        invite_token=kwargs.get("invite_token", "token-a"),
        status=kwargs.get("status", "completed"),
    )


def test_score_band_uses_recommendation_when_present():
    assert _score_band("Strong Hire", 60.0) == "Strong Hire"
    assert _score_band(None, 88.0) == "Strong Hire"
    assert _score_band(None, None) == "Unscored"


def test_matches_filters_by_role_and_score_band():
    summary = _summary(role_title="Senior Backend Engineer", final_score=72.0, recommendation="Hire")
    row = _row(invite_token="token-a")
    assert _matches_filters(
        summary,
        row,
        RecruiterSessionFilters(role_title="backend", score_band="Hire"),
    )
    assert not _matches_filters(
        summary,
        row,
        RecruiterSessionFilters(role_title="frontend"),
    )


def test_per_assessment_metrics_counts_completed_and_flags():
    invite = SimpleNamespace(
        token="token-a",
        jd_text="Backend Engineer role",
        difficulty="Medium",
        questions_json=[{"text": "Q1", "type": "subjective"}],
        used_count=2,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    summary = _summary(
        invite_token="token-a",
        final_score=55.0,
        recommendation="Maybe",
        human_review_flag=True,
        integrity_level="serious_concerns",
    )
    row = _row(invite_token="token-a")
    service = RecruiterAnalyticsService(db=SimpleNamespace())
    metrics = service._per_assessment_metrics(
        [invite],
        [row],
        [(row, summary)],
    )
    assert len(metrics) == 1
    assert metrics[0].completed_count == 1
    assert metrics[0].integrity_flag_count == 1
    assert metrics[0].average_score == 55.0


def test_export_sessions_csv_includes_header_and_row(monkeypatch):
    summary = _summary()
    row = _row(invite_token="token-a", session_id=summary.session_id)

    class FakeAnalyticsService:
        async def list_filtered_sessions(self, recruiter_id, filters=None):
            return [summary]

    async def fake_list(*args, **kwargs):
        return [summary]

    monkeypatch.setattr(
        analytics_module.RecruiterAnalyticsService,
        "list_filtered_sessions",
        fake_list,
    )

    import asyncio

    service = RecruiterAnalyticsService(db=SimpleNamespace())
    csv_text, filename = asyncio.run(service.export_sessions_csv(1))
    assert filename.startswith("recruiter-sessions-")
    assert "session_id,candidate_name,role_title" in csv_text
    assert "Backend Engineer" in csv_text
