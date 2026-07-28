"""Phase 5: adaptive interview blueprint, coverage tracking, and follow-ups.

Invite/assessment sessions keep fixed question banks. Open AI interviews may
replace upcoming subjective questions based on answer quality and coverage gaps.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.core.config import settings
from app.services.question_utils import normalize_question, question_text, question_type

logger = logging.getLogger(__name__)

PROMPT_VERSION = "phase5-v1"
DIFFICULTY_ORDER = ("junior", "mid", "senior")

DEFAULT_COMPETENCIES = (
    "fundamentals",
    "problem_solving",
    "system_design",
    "communication",
    "role_fit",
)

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "python": ("python", "django", "flask", "fastapi"),
    "javascript": ("javascript", "typescript", "node", "react", "frontend"),
    "backend": ("api", "backend", "microservice", "rest", "graphql"),
    "databases": ("sql", "postgres", "database", "redis", "mongodb"),
    "system_design": ("scale", "architecture", "system design", "distributed"),
    "devops": ("docker", "kubernetes", "ci/cd", "aws", "deploy"),
    "security": ("security", "auth", "oauth", "encryption"),
    "testing": ("test", "pytest", "unit test", "qa"),
}


def adaptive_enabled() -> bool:
    return bool(getattr(settings, "ADAPTIVE_INTERVIEW_ENABLED", True))


def normalize_difficulty(level: str | None) -> str:
    raw = (level or "mid").strip().lower()
    aliases = {
        "easy": "junior",
        "beginner": "junior",
        "entry": "junior",
        "medium": "mid",
        "intermediate": "mid",
        "hard": "senior",
        "advanced": "senior",
        "expert": "senior",
    }
    mapped = aliases.get(raw, raw)
    return mapped if mapped in DIFFICULTY_ORDER else "mid"


def judgment_quality(judgment: dict[str, Any] | None) -> Optional[float]:
    if not isinstance(judgment, dict) or judgment.get("error"):
        return None
    raw = judgment.get("weighted_total")
    if isinstance(raw, (int, float)):
        return max(0.0, min(100.0, float(raw)))
    score = judgment.get("score")
    if isinstance(score, (int, float)):
        return max(0.0, min(100.0, float(score)))
    return None


def adjust_difficulty(current: str, quality: float | None) -> str:
    level = normalize_difficulty(current)
    if quality is None:
        return level
    low = float(getattr(settings, "ADAPTIVE_QUALITY_LOW", 55) or 55)
    high = float(getattr(settings, "ADAPTIVE_QUALITY_HIGH", 80) or 80)
    idx = DIFFICULTY_ORDER.index(level)
    if quality < low and idx > 0:
        return DIFFICULTY_ORDER[idx - 1]
    if quality >= high and idx < len(DIFFICULTY_ORDER) - 1:
        return DIFFICULTY_ORDER[idx + 1]
    return level


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}


def infer_topics(
    *,
    role_title: str,
    topic_focus: str | None,
    job_description: str | None,
    resume_text: str | None = None,
) -> list[str]:
    blob = " ".join(
        part
        for part in (role_title, topic_focus or "", job_description or "", resume_text or "")
        if part
    ).lower()
    tokens = _tokenize(blob)
    found: list[str] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(k in blob or k in tokens for k in keywords):
            found.append(topic)
    if topic_focus and topic_focus.strip():
        focus = topic_focus.strip().lower().replace(" ", "_")[:40]
        if focus not in found:
            found.insert(0, focus)
    if not found:
        found = ["fundamentals", "problem_solving", "role_fit"]
    # Stable unique order, capped for coverage tracking.
    deduped: list[str] = []
    for topic in found:
        if topic not in deduped:
            deduped.append(topic)
    return deduped[:6]


def build_blueprint(
    *,
    role_title: str,
    experience_level: str,
    question_count: int,
    topic_focus: str | None = None,
    job_description: str | None = None,
    resume_text: str | None = None,
) -> dict[str, Any]:
    topics = infer_topics(
        role_title=role_title,
        topic_focus=topic_focus,
        job_description=job_description,
        resume_text=resume_text,
    )
    difficulty = normalize_difficulty(experience_level)
    competencies = list(DEFAULT_COMPETENCIES)
    must_hit = topics[: min(3, len(topics))] or ["fundamentals"]
    return {
        "prompt_version": PROMPT_VERSION,
        "role_title": role_title,
        "target_difficulty": difficulty,
        "question_count": question_count,
        "topics": topics,
        "must_hit_competencies": must_hit,
        "competencies": competencies,
        "topic_focus": topic_focus,
    }


def initial_adaptive_state(blueprint: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": True,
        "prompt_version": PROMPT_VERSION,
        "blueprint": blueprint,
        "current_difficulty": blueprint.get("target_difficulty", "mid"),
        "coverage": {topic: 0 for topic in blueprint.get("topics", [])},
        "competency_hits": {
            c: 0 for c in blueprint.get("must_hit_competencies", [])
        },
        "adaptations": [],
    }


def assign_topic_for_index(blueprint: dict[str, Any], index: int) -> str:
    topics = list(blueprint.get("topics") or ["fundamentals"])
    return topics[index % len(topics)]


def enrich_seed_questions(
    questions: list[Any],
    blueprint: dict[str, Any],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for i, raw in enumerate(questions):
        q = normalize_question(raw)
        topic = assign_topic_for_index(blueprint, i)
        adaptive_meta = dict(q.get("adaptive") or {}) if isinstance(q.get("adaptive"), dict) else {}
        adaptive_meta.update(
            {
                "topic": topic,
                "difficulty": blueprint.get("target_difficulty", "mid"),
                "source": "seed",
                "competency": blueprint.get("must_hit_competencies", ["fundamentals"])[
                    i % max(1, len(blueprint.get("must_hit_competencies") or ["fundamentals"]))
                ],
            }
        )
        q["adaptive"] = adaptive_meta
        enriched.append(q)
    return enriched


def question_adaptive_meta(item: Any) -> dict[str, Any]:
    if isinstance(item, dict) and isinstance(item.get("adaptive"), dict):
        return dict(item["adaptive"])
    return {}


def is_invite_locked(session: Any) -> bool:
    token = getattr(session, "invite_token", None)
    return bool(token and str(token).strip())


def should_adapt_session(session: Any) -> bool:
    if not adaptive_enabled():
        return False
    if is_invite_locked(session):
        return False
    state = getattr(session, "adaptive_state", None)
    if not isinstance(state, dict) or not state.get("enabled"):
        return False
    return True


def pick_follow_up_focus(
    state: dict[str, Any],
    judgment: dict[str, Any] | None,
) -> dict[str, str]:
    blueprint = state.get("blueprint") or {}
    coverage = dict(state.get("coverage") or {})
    must_hit = list(blueprint.get("must_hit_competencies") or [])
    competencies = dict(state.get("competency_hits") or {})

    # Prefer uncovered must-hit topics/competencies.
    uncovered = [t for t, n in coverage.items() if int(n or 0) <= 0]
    topic = uncovered[0] if uncovered else None
    if topic is None and coverage:
        topic = min(coverage.items(), key=lambda kv: int(kv[1] or 0))[0]
    if topic is None:
        topics = list(blueprint.get("topics") or ["fundamentals"])
        topic = topics[0]

    competency = None
    for c in must_hit:
        if int(competencies.get(c, 0) or 0) <= 0:
            competency = c
            break
    if competency is None and must_hit:
        competency = must_hit[0]
    if competency is None:
        competency = "problem_solving"

    improvements: list[str] = []
    if isinstance(judgment, dict):
        raw = judgment.get("improvements") or []
        if isinstance(raw, list):
            improvements = [str(x).strip() for x in raw if str(x).strip()][:3]

    quality = judgment_quality(judgment)
    low = float(getattr(settings, "ADAPTIVE_QUALITY_LOW", 55) or 55)
    mode = "probe_gap"
    if quality is not None and quality >= float(
        getattr(settings, "ADAPTIVE_QUALITY_HIGH", 80) or 80
    ):
        mode = "go_deeper"
    elif quality is not None and quality < low:
        mode = "scaffold"

    return {
        "topic": topic,
        "competency": competency,
        "mode": mode,
        "weak_area": improvements[0] if improvements else competency.replace("_", " "),
    }


def record_coverage(
    state: dict[str, Any],
    answered_question: Any,
) -> dict[str, Any]:
    meta = question_adaptive_meta(answered_question)
    topic = str(meta.get("topic") or "fundamentals")
    competency = str(meta.get("competency") or "problem_solving")
    coverage = dict(state.get("coverage") or {})
    coverage[topic] = int(coverage.get(topic, 0) or 0) + 1
    hits = dict(state.get("competency_hits") or {})
    hits[competency] = int(hits.get(competency, 0) or 0) + 1
    state["coverage"] = coverage
    state["competency_hits"] = hits
    return state


def maybe_adapt_next_question(
    session: Any,
    *,
    answered_index: int,
    judgment: dict[str, Any] | None,
    generate_follow_up,
) -> bool:
    """Replace the next remaining subjective question when adaptive mode applies.

    Returns True if the next question was changed.
    """
    if not should_adapt_session(session):
        return False

    next_index = answered_index + 1
    questions = list(session.questions or [])
    if next_index >= len(questions):
        return False

    next_q = questions[next_index]
    if question_type(next_q) != "subjective":
        return False

    # Do not rewrite already-answered slots (safety).
    if next_index < len(getattr(session, "answers", []) or []):
        return False

    state = dict(session.adaptive_state or {})
    state = record_coverage(state, questions[answered_index])
    quality = judgment_quality(judgment)
    new_difficulty = adjust_difficulty(
        str(state.get("current_difficulty") or "mid"),
        quality,
    )
    state["current_difficulty"] = new_difficulty
    focus = pick_follow_up_focus(state, judgment)

    prior_q = question_text(questions[answered_index])
    prior_a = ""
    if answered_index < len(getattr(session, "answers", []) or []):
        prior_a = str(session.answers[answered_index] or "")

    try:
        follow_up_text = generate_follow_up(
            role_title=session.role_title,
            experience_level=new_difficulty,
            topic=focus["topic"],
            competency=focus["competency"],
            mode=focus["mode"],
            weak_area=focus["weak_area"],
            prior_question=prior_q,
            prior_answer=prior_a,
            job_description=getattr(session, "job_description", None),
            resume_text=getattr(session, "resume_text", None),
        )
    except Exception:
        logger.exception("Adaptive follow-up generation failed; keeping seed question")
        session.adaptive_state = state
        return False

    text = (follow_up_text or "").strip()
    if not text:
        session.adaptive_state = state
        return False

    adapted = normalize_question(next_q)
    adapted["text"] = text
    adapted["type"] = "subjective"
    adapted["adaptive"] = {
        "topic": focus["topic"],
        "competency": focus["competency"],
        "difficulty": new_difficulty,
        "source": "adaptive_follow_up",
        "mode": focus["mode"],
        "from_question_index": answered_index,
        "quality_signal": quality,
    }
    questions[next_index] = adapted
    session.questions = questions

    adaptations = list(state.get("adaptations") or [])
    adaptations.append(
        {
            "at_index": next_index,
            "from_question_index": answered_index,
            "topic": focus["topic"],
            "competency": focus["competency"],
            "difficulty": new_difficulty,
            "mode": focus["mode"],
            "quality_signal": quality,
        }
    )
    state["adaptations"] = adaptations[-20:]
    session.adaptive_state = state
    return True


def public_adaptive_flags(item: Any) -> dict[str, Any]:
    meta = question_adaptive_meta(item)
    source = str(meta.get("source") or "seed")
    return {
        "is_adaptive_follow_up": source == "adaptive_follow_up",
        "adaptive_topic": meta.get("topic"),
        "adaptive_difficulty": meta.get("difficulty"),
    }


def adaptive_summary_for_recruiter(state: Any) -> dict[str, Any] | None:
    if not isinstance(state, dict) or not state:
        return None
    blueprint = state.get("blueprint") or {}
    return {
        "enabled": bool(state.get("enabled")),
        "prompt_version": state.get("prompt_version") or PROMPT_VERSION,
        "target_difficulty": blueprint.get("target_difficulty"),
        "current_difficulty": state.get("current_difficulty"),
        "topics": list(blueprint.get("topics") or []),
        "must_hit_competencies": list(blueprint.get("must_hit_competencies") or []),
        "coverage": dict(state.get("coverage") or {}),
        "competency_hits": dict(state.get("competency_hits") or {}),
        "adaptation_count": len(state.get("adaptations") or []),
        "adaptations": list(state.get("adaptations") or [])[-10:],
    }
