#!/usr/bin/env python3
"""Create ORM tables and align Alembic revision state for fresh or existing databases."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(ROOT / ".env")

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
import app.db.candidate_verification_model  # noqa: F401, E402
import app.db.evidence_model  # noqa: F401, E402
import app.db.interview_invite_model  # noqa: F401, E402
import app.db.session_model  # noqa: F401, E402
import app.models.user  # noqa: F401, E402


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    return url


def _alembic_version() -> str | None:
    sync_url = _sync_database_url()
    eng = create_engine(sync_url)
    try:
        with eng.connect() as conn:
            if conn.dialect.name == "sqlite":
                row = conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
                ).fetchone()
                if not row:
                    return None
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
            return row[0] if row else None
    except Exception:
        return None
    finally:
        eng.dispose()


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def main() -> int:
    cfg = Config(str(ROOT / "alembic.ini"))
    current = _alembic_version()

    if current is None:
        print("==> Fresh database — creating tables from ORM models...")
        asyncio.run(_create_all())
        print("==> Stamping Alembic head...")
        command.stamp(cfg, "head")
    else:
        print(f"==> Existing Alembic revision {current} — running upgrades...")
        command.upgrade(cfg, "head")

    print("Database bootstrap complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
