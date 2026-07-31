"""Helpers for invite/session question objects (text, type, timer, marks)."""

from __future__ import annotations

import json
import random
import re
from typing import Any

from app.core.config import settings

DEFAULT_QUESTION_MARKS = 10
MIN_ASSESSMENT_QUESTIONS = 2
MAX_ASSESSMENT_QUESTIONS = 20

QUESTION_TYPES = ("subjective", "mcq", "msq", "numerical", "coding")
OBJECTIVE_TYPES = frozenset({"mcq", "msq", "numerical"})
CODING_TYPE = "coding"

SUPPORTED_CODING_LANGS = ("c", "cpp", "python", "perl", "java", "javascript")


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


def question_type(item: Any) -> str:
    if isinstance(item, dict):
        raw = str(item.get("type", item.get("question_type", "subjective")) or "subjective")
        normalized = raw.strip().lower()
        if normalized in QUESTION_TYPES:
            return normalized
    return "subjective"


def question_options(item: Any) -> list[str]:
    if not isinstance(item, dict):
        return []
    raw = item.get("options")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for opt in raw:
        text = str(opt).strip() if opt is not None else ""
        if text:
            out.append(text)
    return out


def question_correct_indices(item: Any) -> list[int]:
    if not isinstance(item, dict):
        return []
    options = question_options(item)
    raw = item.get("correct_indices")
    indices: list[int] = []
    if isinstance(raw, list):
        for value in raw:
            try:
                idx = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(options) and idx not in indices:
                indices.append(idx)
    elif isinstance(raw, (int, float)):
        idx = int(raw)
        if 0 <= idx < len(options):
            indices = [idx]

    # Legacy: correct_answer as option text or single index string
    if not indices and item.get("correct_answer") is not None and options:
        ca = item.get("correct_answer")
        if isinstance(ca, (int, float)) and not isinstance(ca, bool):
            idx = int(ca)
            if 0 <= idx < len(options):
                indices = [idx]
        else:
            ca_text = str(ca).strip().lower()
            for i, opt in enumerate(options):
                if opt.strip().lower() == ca_text and i not in indices:
                    indices.append(i)
    return indices


def question_correct_answer(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    raw = item.get("correct_answer")
    if raw is None:
        return None
    text = str(raw).strip()
    return text if text else None


def question_tolerance(item: Any) -> float:
    if not isinstance(item, dict):
        return 0.0
    raw = item.get("tolerance")
    try:
        value = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, value)


def _normalize_coding_lang(raw: Any) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower()
    aliases = {
        "c++": "cpp",
        "py": "python",
        "python3": "python",
        "js": "javascript",
        "node": "javascript",
        "nodejs": "javascript",
    }
    key = aliases.get(key, key)
    return key if key in SUPPORTED_CODING_LANGS else None


def question_coding_languages(item: Any) -> list[str]:
    if not isinstance(item, dict):
        return ["python"]
    raw = item.get("languages") or item.get("language")
    langs: list[str] = []
    if isinstance(raw, list):
        for value in raw:
            normalized = _normalize_coding_lang(value)
            if normalized and normalized not in langs:
                langs.append(normalized)
    elif isinstance(raw, str):
        normalized = _normalize_coding_lang(raw)
        if normalized:
            langs.append(normalized)
    return langs or ["python"]


def question_starter_code(item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        return {}
    raw = item.get("starter_code") or item.get("starter")
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            lang = _normalize_coding_lang(key)
            if lang and value is not None:
                out[lang] = str(value)
    elif isinstance(raw, str) and raw.strip():
        langs = question_coding_languages(item)
        out[langs[0]] = raw
    return out


def _normalize_tests(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        stdin = str(item.get("stdin", item.get("input", "")) or "")
        expected = str(
            item.get("expected_stdout", item.get("expected", item.get("output", "")))
            or ""
        )
        out.append({"stdin": stdin, "expected_stdout": expected})
    return out


def question_public_tests(item: Any) -> list[dict[str, str]]:
    if not isinstance(item, dict):
        return []
    return _normalize_tests(item.get("public_tests") or item.get("sample_tests"))


def question_hidden_tests(item: Any) -> list[dict[str, str]]:
    if not isinstance(item, dict):
        return []
    return _normalize_tests(item.get("hidden_tests") or item.get("private_tests"))


def question_time_limit_ms(item: Any) -> int:
    if isinstance(item, dict):
        raw = item.get("time_limit_ms")
        if isinstance(raw, (int, float)) and raw > 0:
            return max(500, min(int(raw), 5000))
    return 2000


def question_memory_limit_mb(item: Any) -> int:
    if isinstance(item, dict):
        raw = item.get("memory_limit_mb")
        if isinstance(raw, (int, float)) and raw > 0:
            return max(32, min(int(raw), 256))
    return 128


def normalize_question(item: Any) -> dict[str, Any]:
    """Normalize to a full question object including type metadata."""
    text = question_text(item)
    qtype = question_type(item)
    options = question_options(item) if qtype in ("mcq", "msq") else []
    correct_indices = question_correct_indices(item) if qtype in ("mcq", "msq") else []
    if qtype == "mcq" and len(correct_indices) > 1:
        correct_indices = correct_indices[:1]
    correct_answer = question_correct_answer(item) if qtype == "numerical" else None
    tolerance = question_tolerance(item) if qtype == "numerical" else 0.0

    payload: dict[str, Any] = {
        "text": text,
        "type": qtype,
        "time_seconds": question_time_seconds(item),
        "marks": question_marks(item),
    }
    if qtype in ("mcq", "msq"):
        payload["options"] = options
        payload["correct_indices"] = correct_indices
    if qtype == "numerical":
        payload["correct_answer"] = correct_answer or ""
        payload["tolerance"] = tolerance
    if qtype == "coding":
        payload["languages"] = question_coding_languages(item)
        payload["starter_code"] = question_starter_code(item)
        payload["public_tests"] = question_public_tests(item)
        payload["hidden_tests"] = question_hidden_tests(item)
        payload["time_limit_ms"] = question_time_limit_ms(item)
        payload["memory_limit_mb"] = question_memory_limit_mb(item)
        if isinstance(item, dict) and item.get("rubric_notes"):
            payload["rubric_notes"] = str(item.get("rubric_notes"))
    return payload


def normalize_questions(items: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items or []:
        normalized = normalize_question(item)
        if normalized["text"]:
            out.append(normalized)
    return out


def questions_as_text_list(items: list[Any] | None) -> list[str]:
    return [q["text"] for q in normalize_questions(items)]


def shuffle_options(options: list[str], *, seed: str | None = None) -> list[str]:
    """Return a shuffled copy of options (stable when seed is provided)."""
    if len(options) <= 1:
        return list(options)
    shuffled = list(options)
    rng = random.Random(seed) if seed is not None else random.Random()
    rng.shuffle(shuffled)
    return shuffled


def public_question_view(
    item: Any,
    *,
    shuffle_seed: str | None = None,
) -> dict[str, Any]:
    """Candidate-safe question payload (no correct answers / hidden tests)."""
    q = normalize_question(item)
    view: dict[str, Any] = {
        "text": q["text"],
        "type": q["type"],
        "time_seconds": q["time_seconds"],
        "marks": q["marks"],
    }
    if q["type"] in ("mcq", "msq"):
        options = list(q.get("options") or [])
        view["options"] = shuffle_options(options, seed=shuffle_seed)
    if q["type"] == "numerical":
        view["tolerance"] = float(q.get("tolerance") or 0.0)
    if q["type"] == "coding":
        view["languages"] = list(q.get("languages") or ["python"])
        view["starter_code"] = dict(q.get("starter_code") or {})
        view["public_tests"] = list(q.get("public_tests") or [])
        view["time_limit_ms"] = int(q.get("time_limit_ms") or 2000)
        view["memory_limit_mb"] = int(q.get("memory_limit_mb") or 128)
        # Never expose hidden_tests
    return view


def _parse_float(value: str) -> float | None:
    cleaned = value.strip().replace(",", "")
    cleaned = re.sub(r"[^\d.\-eE+]", "", cleaned)
    if not cleaned or cleaned in {".", "-", "+", "-.", "+."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _selected_texts_from_answer(answer: str, options: list[str]) -> list[str]:
    """Resolve candidate answer string into selected option texts."""
    raw = (answer or "").strip()
    if not raw or not options:
        return []

    # JSON array of strings or indices
    if raw.startswith("["):
        try:
            payload = json.loads(raw)
            if isinstance(payload, list):
                texts: list[str] = []
                for item in payload:
                    if isinstance(item, (int, float)) and not isinstance(item, bool):
                        idx = int(item)
                        if 0 <= idx < len(options):
                            texts.append(options[idx])
                    else:
                        text = str(item).strip()
                        if text:
                            texts.append(text)
                return texts
        except json.JSONDecodeError:
            pass

    # Pipe / newline separated multi-select
    if "|" in raw or "\n" in raw:
        parts = re.split(r"[|\n]+", raw)
        return [p.strip() for p in parts if p.strip()]

    # Single index
    if re.fullmatch(r"\d+", raw):
        idx = int(raw)
        if 0 <= idx < len(options):
            return [options[idx]]

    # Comma-separated indices
    if re.fullmatch(r"[\d,\s]+", raw) and "," in raw:
        texts = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(options):
                    texts.append(options[idx])
        if texts:
            return texts

    return [raw]


def grade_objective_answer(question: Any, answer: str) -> dict[str, Any] | None:
    """Grade MCQ / MSQ / numerical answers server-side. Returns None for subjective."""
    q = normalize_question(question)
    qtype = q["type"]
    if qtype not in OBJECTIVE_TYPES:
        return None

    marks = float(q["marks"])
    answer_text = (answer or "").strip()

    if qtype == "numerical":
        expected_raw = str(q.get("correct_answer") or "").strip()
        expected = _parse_float(expected_raw)
        actual = _parse_float(answer_text)
        tolerance = float(q.get("tolerance") or 0.0)
        if expected is None or actual is None:
            score = 0.0
            reasoning = "Numerical answer could not be parsed or expected answer is missing."
            correct = False
        else:
            correct = abs(actual - expected) <= tolerance + 1e-9
            score = 100.0 if correct else 0.0
            reasoning = (
                f"Correct within tolerance +/-{tolerance}."
                if correct
                else f"Expected {expected_raw} (+/-{tolerance}); received {answer_text}."
            )
        return {
            "weighted_total": score,
            "overall_reasoning": reasoning,
            "strengths": ["Exact match"] if correct else [],
            "improvements": [] if correct else ["Review the expected numerical result."],
            "criteria_scores": {
                "objective": {
                    "score": score,
                    "reasoning": reasoning,
                }
            },
            "grading_mode": "objective_numerical",
            "is_correct": correct,
            "max_marks": marks,
        }

    options = list(q.get("options") or [])
    correct_indices = list(q.get("correct_indices") or [])
    correct_texts = {
        options[i].strip().lower()
        for i in correct_indices
        if 0 <= i < len(options)
    }
    selected = _selected_texts_from_answer(answer_text, options)
    selected_norm = {t.strip().lower() for t in selected if t.strip()}

    if qtype == "mcq":
        correct = len(correct_texts) == 1 and selected_norm == correct_texts
        score = 100.0 if correct else 0.0
        reasoning = (
            "Selected the correct option."
            if correct
            else "Incorrect option selected."
        )
        return {
            "weighted_total": score,
            "overall_reasoning": reasoning,
            "strengths": ["Correct selection"] if correct else [],
            "improvements": [] if correct else ["Review the concept covered by this MCQ."],
            "criteria_scores": {
                "objective": {"score": score, "reasoning": reasoning}
            },
            "grading_mode": "objective_mcq",
            "is_correct": correct,
            "max_marks": marks,
        }

    # MSQ — all-or-nothing exact set match
    correct = bool(correct_texts) and selected_norm == correct_texts
    score = 100.0 if correct else 0.0
    reasoning = (
        "Selected exactly the correct set of options."
        if correct
        else "Multi-select answer did not match the expected option set."
    )
    return {
        "weighted_total": score,
        "overall_reasoning": reasoning,
        "strengths": ["Correct multi-select"] if correct else [],
        "improvements": [] if correct else ["Review which options apply; all must be selected."],
        "criteria_scores": {
            "objective": {"score": score, "reasoning": reasoning}
        },
        "grading_mode": "objective_msq",
        "is_correct": correct,
        "max_marks": marks,
    }
