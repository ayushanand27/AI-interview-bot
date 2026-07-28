"""Phase 5 adaptive interview unit tests."""

from types import SimpleNamespace
from uuid import uuid4

from app.services.adaptive_interview import (
    adjust_difficulty,
    build_blueprint,
    enrich_seed_questions,
    initial_adaptive_state,
    is_invite_locked,
    judgment_quality,
    maybe_adapt_next_question,
    pick_follow_up_focus,
    public_adaptive_flags,
    should_adapt_session,
)
from app.services.recruiter_service import _session_to_detail


def test_build_blueprint_infers_topics_and_must_hit():
    blueprint = build_blueprint(
        role_title="Backend Engineer",
        experience_level="senior",
        question_count=5,
        topic_focus="Python APIs",
        job_description="Build FastAPI services with Postgres and Redis.",
    )
    assert blueprint["target_difficulty"] == "senior"
    assert blueprint["prompt_version"] == "phase5-v1"
    assert "python" in blueprint["topics"] or "Python APIs".lower().replace(" ", "_") in blueprint["topics"]
    assert len(blueprint["must_hit_competencies"]) >= 1
    assert blueprint["question_count"] == 5


def test_enrich_seed_questions_tags_topics():
    blueprint = build_blueprint(
        role_title="Backend Engineer",
        experience_level="mid",
        question_count=3,
        topic_focus="databases",
        job_description="SQL and Postgres experience required.",
    )
    enriched = enrich_seed_questions(
        ["Explain indexes", "Describe transactions", "Talk about caching"],
        blueprint,
    )
    assert len(enriched) == 3
    assert all(q["adaptive"]["source"] == "seed" for q in enriched)
    assert enriched[0]["adaptive"]["topic"]


def test_adjust_difficulty_moves_within_bounds():
    assert adjust_difficulty("mid", 40) == "junior"
    assert adjust_difficulty("mid", 90) == "senior"
    assert adjust_difficulty("junior", 40) == "junior"
    assert adjust_difficulty("senior", 95) == "senior"
    assert adjust_difficulty("mid", 70) == "mid"


def test_invite_sessions_do_not_adapt():
    session = SimpleNamespace(
        invite_token="abc-123",
        adaptive_state={"enabled": True},
        questions=[],
        answers=[],
    )
    assert is_invite_locked(session) is True
    assert should_adapt_session(session) is False


def test_maybe_adapt_next_question_rewrites_upcoming_subjective(monkeypatch):
    monkeypatch.setenv("ADAPTIVE_INTERVIEW_ENABLED", "true")
    blueprint = build_blueprint(
        role_title="Backend Engineer",
        experience_level="mid",
        question_count=2,
        topic_focus="APIs",
        job_description="REST APIs",
    )
    questions = enrich_seed_questions(["Q1 seed", "Q2 seed"], blueprint)
    session = SimpleNamespace(
        invite_token=None,
        role_title="Backend Engineer",
        job_description="REST APIs",
        resume_text=None,
        adaptive_state=initial_adaptive_state(blueprint),
        questions=questions,
        answers=["A solid answer about REST"],
    )

    changed = maybe_adapt_next_question(
        session,
        answered_index=0,
        judgment={
            "weighted_total": 42,
            "improvements": ["Need more concrete API examples"],
        },
        generate_follow_up=lambda **_kwargs: "Can you walk through a concrete REST pagination design?",
    )
    assert changed is True
    assert session.questions[1]["text"].startswith("Can you walk through")
    assert session.questions[1]["adaptive"]["source"] == "adaptive_follow_up"
    assert session.adaptive_state["adaptations"]
    flags = public_adaptive_flags(session.questions[1])
    assert flags["is_adaptive_follow_up"] is True


def test_maybe_adapt_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.services.adaptive_interview.adaptive_enabled",
        lambda: False,
    )
    session = SimpleNamespace(
        invite_token=None,
        adaptive_state={"enabled": True},
        questions=[{"text": "Q1", "type": "subjective"}, {"text": "Q2", "type": "subjective"}],
        answers=["ans"],
    )
    changed = maybe_adapt_next_question(
        session,
        answered_index=0,
        judgment={"weighted_total": 50},
        generate_follow_up=lambda **_kwargs: "should not run",
    )
    assert changed is False
    assert session.questions[1]["text"] == "Q2"


def test_pick_follow_up_prefers_uncovered_topic():
    state = {
        "blueprint": {
            "topics": ["python", "databases"],
            "must_hit_competencies": ["fundamentals", "problem_solving"],
        },
        "coverage": {"python": 1, "databases": 0},
        "competency_hits": {"fundamentals": 1, "problem_solving": 0},
        "current_difficulty": "mid",
    }
    focus = pick_follow_up_focus(state, {"weighted_total": 50, "improvements": ["SQL joins"]})
    assert focus["topic"] == "databases"
    assert focus["competency"] == "problem_solving"
    assert focus["mode"] == "scaffold"


def test_judgment_quality_handles_missing():
    assert judgment_quality(None) is None
    assert judgment_quality({"error": "judging_failed"}) is None
    assert judgment_quality({"weighted_total": 77}) == 77.0


def test_session_detail_includes_adaptive_summary(monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(
        "app.services.recruiter_service.get_session_review_state",
        lambda _session_id: {
            "human_review_required": False,
            "review_status": "cleared",
            "review_notes": None,
            "reviewed_at": None,
            "reviewed_by_user_id": None,
        },
    )
    monkeypatch.setattr(
        "app.services.recruiter_service.list_proctor_events",
        lambda _session_id: [],
    )

    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        session_id=uuid4(),
        resume_filename="candidate_resume.pdf",
        role_title="Backend Engineer",
        experience_level="mid",
        status="completed",
        updated_at=now,
        created_at=now,
        questions=[
            {
                "text": "Seed question",
                "type": "subjective",
                "adaptive": {"source": "seed", "topic": "python"},
            },
            {
                "text": "Adapted follow-up",
                "type": "subjective",
                "adaptive": {
                    "source": "adaptive_follow_up",
                    "topic": "databases",
                },
            },
        ],
        answers=["a1", "a2"],
        answer_judgments=[{"weighted_total": 70}, {"weighted_total": 80}],
        total_questions=2,
        final_score={"final_score": 75},
        proctoring_summary={},
        recording_filename=None,
        human_review_flag=False,
        adaptive_state={
            "enabled": True,
            "prompt_version": "phase5-v1",
            "blueprint": {
                "target_difficulty": "mid",
                "topics": ["python", "databases"],
                "must_hit_competencies": ["fundamentals"],
            },
            "current_difficulty": "senior",
            "coverage": {"python": 1, "databases": 1},
            "competency_hits": {"fundamentals": 1},
            "adaptations": [{"at_index": 1}],
        },
    )
    detail = _session_to_detail(row, None)
    assert detail.adaptive_interview is not None
    assert detail.adaptive_interview["adaptation_count"] == 1
    assert detail.transcript[1].is_adaptive_follow_up is True
    assert detail.transcript[1].adaptive_topic == "databases"
