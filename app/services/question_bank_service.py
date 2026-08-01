"""Question bank retrieval, skill tagging, and usage tracking."""

from __future__ import annotations

import hashlib
import random
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import and_, create_engine, select
from sqlalchemy.orm import sessionmaker as sync_sessionmaker

from app.core.config import settings
from app.db.question_bank_model import QuestionBankItem, QuestionBankUsage

USAGE_COOLDOWN_DAYS = 30

_SKILL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "arrays": ("array", "arrays", "list", "vector"),
    "hashmap": ("hash", "map", "dictionary", "hashtable"),
    "strings": ("string", "strings", "anagram", "palindrome"),
    "stack": ("stack", "parentheses", "bracket"),
    "queue": ("queue", "deque", "message queue", "broker"),
    "heap": ("heap", "priority queue", "top k"),
    "trees": ("tree", "bst", "binary tree", "trie"),
    "graphs": ("graph", "bfs", "dfs", "shortest path"),
    "dp": ("dynamic programming", "dp", "memoization"),
    "binary-search": ("binary search", "sorted array"),
    "two-pointers": ("two pointer", "sliding window"),
    "backend": ("api", "rest", "microservice", "backend", "fastapi", "django", "spring"),
    "frontend": ("react", "frontend", "ui", "typescript", "javascript"),
    "databases": ("sql", "postgres", "mysql", "database", "index", "orm"),
    "system-design": ("scalability", "distributed", "cache", "load balancer", "cap theorem"),
    "devops": ("ci/cd", "docker", "kubernetes", "deploy", "observability"),
    "security": ("security", "auth", "oauth", "encryption", "secrets"),
    "testing": ("test", "qa", "tdd", "unit test", "integration test"),
    "cloud": ("aws", "gcp", "azure", "cloud", "s3", "lambda"),
    "python": ("python", "django", "flask", "fastapi"),
    "java": ("java", "spring", "jvm"),
    "cpp": ("c++", "cpp"),
    "data": ("data engineer", "etl", "spark", "warehouse", "analytics"),
}


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


@lru_cache(maxsize=1)
def _get_sync_session_local():
    engine = create_engine(_sync_database_url(), pool_pre_ping=True)
    return sync_sessionmaker(bind=engine, expire_on_commit=False)


def fingerprint_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").lower()).strip()
    cleaned = re.split(r"\bexample\s*1\b", cleaned, maxsplit=1)[0].strip()
    return cleaned[:180]


def stable_slug(prefix: str, title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "item"
    digest = hashlib.sha1(f"{prefix}:{title}".encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{base}-{digest}"


def extract_skill_tags(jd_text: str) -> list[str]:
    text = (jd_text or "").lower()
    found: list[str] = []
    for tag, keywords in _SKILL_KEYWORDS.items():
        if any(k in text for k in keywords):
            found.append(tag)
    if not found:
        found = ["backend", "testing", "system-design", "arrays", "hashmap"]
    return found


def _difficulty_rank(value: str) -> int:
    return {"Easy": 0, "Medium": 1, "Hard": 2}.get(value, 1)


def _payload_to_question(item: QuestionBankItem) -> dict[str, Any]:
    payload = dict(item.payload or {})
    payload["text"] = payload.get("text") or item.prompt_text
    payload["type"] = item.type
    payload["bank_id"] = item.id
    payload["origin"] = "library"
    return payload


def retrieve_bank_questions(
    *,
    question_types: list[str],
    difficulty: str,
    skill_tags: list[str],
    limit_per_type: int,
    recruiter_id: int | None = None,
    exclude_fingerprints: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return bank questions grouped by type, best-effort skill match."""
    exclude = set(exclude_fingerprints or set())
    skill_set = set(skill_tags or [])
    needed = [t for t in question_types if t]
    if not needed:
        return {}

    out: dict[str, list[dict[str, Any]]] = {t: [] for t in needed}
    try:
        SessionLocal = _get_sync_session_local()
        with SessionLocal() as db:
            recent_ids: set[int] = set()
            if recruiter_id is not None:
                cutoff = datetime.now(timezone.utc) - timedelta(days=USAGE_COOLDOWN_DAYS)
                rows = db.execute(
                    select(QuestionBankUsage.question_id).where(
                        and_(
                            QuestionBankUsage.recruiter_id == recruiter_id,
                            QuestionBankUsage.used_at >= cutoff,
                        )
                    )
                ).scalars().all()
                recent_ids = set(int(x) for x in rows)

            items = (
                db.execute(
                    select(QuestionBankItem).where(QuestionBankItem.is_active.is_(True))
                )
                .scalars()
                .all()
            )
    except Exception:
        return out

    by_type: dict[str, list[QuestionBankItem]] = {t: [] for t in needed}
    for item in items:
        if item.type not in by_type:
            continue
        if item.id in recent_ids:
            continue
        if item.fingerprint in exclude:
            continue
        by_type[item.type].append(item)

    target_rank = _difficulty_rank(difficulty)

    def score(item: QuestionBankItem) -> tuple:
        tags = set(item.skill_tags or [])
        overlap = len(tags & skill_set)
        diff_pen = abs(_difficulty_rank(item.difficulty) - target_rank)
        return (-overlap, diff_pen, -float(item.quality_score or 0), random.random())

    for qtype, pool in by_type.items():
        ranked = sorted(pool, key=score)
        # Prefer skill overlap > 0, else take best remaining.
        preferred = [i for i in ranked if set(i.skill_tags or []) & skill_set]
        chosen = preferred if preferred else ranked
        for item in chosen[: max(limit_per_type, 1)]:
            out[qtype].append(_payload_to_question(item))
            exclude.add(item.fingerprint)
    return out


def record_question_bank_usage(
    *,
    recruiter_id: int,
    invite_token: str,
    bank_ids: list[int],
) -> None:
    if not bank_ids or not invite_token or recruiter_id is None:
        return
    now = datetime.now(timezone.utc)
    unique_ids = sorted({int(x) for x in bank_ids if x})
    try:
        SessionLocal = _get_sync_session_local()
        with SessionLocal() as db:
            for qid in unique_ids:
                exists = db.execute(
                    select(QuestionBankUsage.id).where(
                        and_(
                            QuestionBankUsage.question_id == qid,
                            QuestionBankUsage.invite_token == invite_token,
                        )
                    )
                ).scalar_one_or_none()
                if exists is not None:
                    continue
                db.add(
                    QuestionBankUsage(
                        question_id=qid,
                        recruiter_id=recruiter_id,
                        invite_token=invite_token,
                        used_at=now,
                    )
                )
            db.commit()
    except Exception:
        return


def count_active_bank_items() -> int:
    try:
        SessionLocal = _get_sync_session_local()
        with SessionLocal() as db:
            return len(
                db.execute(
                    select(QuestionBankItem.id).where(QuestionBankItem.is_active.is_(True))
                )
                .scalars()
                .all()
            )
    except Exception:
        return 0
