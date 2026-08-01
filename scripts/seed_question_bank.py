#!/usr/bin/env python3
"""Upsert curated questions into question_bank from generated seed JSON."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

load_dotenv(ROOT / ".env")

from app.core.config import settings  # noqa: E402
from app.db.question_bank_model import QuestionBankItem  # noqa: E402
from app.services.question_bank_service import fingerprint_text  # noqa: E402

SEED_JSON = ROOT / "app" / "data" / "question_bank_seed.json"


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def main() -> int:
    if not SEED_JSON.exists():
        print(f"Missing seed file: {SEED_JSON}")
        print("Run: python scripts/generate_question_bank_seed.py")
        return 1

    items = json.loads(SEED_JSON.read_text(encoding="utf-8"))
    if not isinstance(items, list) or not items:
        print("Seed JSON is empty")
        return 1

    engine = create_engine(_sync_database_url(), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    inserted = 0
    updated = 0

    with SessionLocal() as db:
        for raw in items:
            slug = str(raw["slug"])
            existing = db.execute(
                select(QuestionBankItem).where(QuestionBankItem.slug == slug)
            ).scalar_one_or_none()
            prompt = str(raw.get("prompt_text") or raw["payload"].get("text") or "")
            fp = fingerprint_text(prompt)
            fields = {
                "type": raw["type"],
                "difficulty": raw["difficulty"],
                "title": raw["title"],
                "prompt_text": prompt,
                "payload": raw["payload"],
                "skill_tags": raw.get("skill_tags") or [],
                "role_tags": raw.get("role_tags") or [],
                "fingerprint": fp,
                "source": raw.get("source") or "seed",
                "is_active": True,
                "quality_score": float(raw.get("quality_score") or 1.0),
                "updated_at": now,
            }
            if existing is None:
                db.add(
                    QuestionBankItem(
                        slug=slug,
                        created_at=now,
                        **fields,
                    )
                )
                inserted += 1
            else:
                for key, value in fields.items():
                    setattr(existing, key, value)
                updated += 1
        db.commit()

    print(f"Seed complete: inserted={inserted} updated={updated} total={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
