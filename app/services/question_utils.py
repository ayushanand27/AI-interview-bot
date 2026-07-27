"""Helpers for invite/session question objects (text, timer, marks)."""

from __future__ import annotations

from typing import Any

from app.core.config import settings

DEFAULT_QUESTION_MARKS = 10
MIN_ASSESSMENT_QUESTIONS = 2
MAX_ASSESSMENT_QUESTIONS = 20


def default_time_seconds() -> int:
    return int(getattr(settings, "QUESTION_TIMER_SECONDS", 180) or 180)


def question_text(item: Any) -> str:
    """Extract display/prompt text from a string or question object."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("text", "question", "content", "prompt"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(item).strip() if item is not None else ""


def question_time_seconds(item: Any) -> int:
    if isinstance(item, dict):
        raw = item.get("time_seconds", item.get("timer_seconds"))
        if isinstance(raw, (int, float)) and raw > 0:
            return max(30, min(int(raw), 3600))
    return default_time_seconds()


def question_marks(item: Any) -> float:
    if isinstance(item, dict):
        raw = item.get("marks", item.get("weight", item.get("max_points")))
        if isinstance(raw, (int, float)) and raw > 0:
            return float(raw)
    return float(DEFAULT_QUESTION_MARKS)


def normalize_question(item: Any) -> dict[str, Any]:
    """Normalize to {text, time_seconds, marks}."""
    text = question_text(item)
    return {
        "text": text,
        "time_seconds": question_time_seconds(item),
        "marks": question_marks(item),
    }


def normalize_questions(items: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items or []:
        normalized = normalize_question(item)
        if normalized["text"]:
            out.append(normalized)
    return out


def questions_as_text_list(items: list[Any] | None) -> list[str]:
    return [q["text"] for q in normalize_questions(items)]
