#!/usr/bin/env python3
"""Documented SQLite → Postgres cutover helpers (non-destructive by default).

Free-tier guidance: keep production on SQLite until RDS is created and verified.
Do NOT wipe the SQLite file. Prefer a fresh Postgres schema via bootstrap_db.py,
then optionally attempt a table dump if you accept the risks.

Safe sequence (recommended):
  1. Create RDS (see docs/P0_AWS_FREE_TIER_SETUP.md)
  2. On EC2, set DATABASE_URL to the RDS URL in a NEW .env.bak first
  3. python scripts/bootstrap_db.py   # against empty RDS
  4. Smoke-test /health and /api/v1/status
  5. Only then switch production DATABASE_URL (pm2 restart)
  6. Keep the old SQLite file as backup for 7+ days

Optional dump (best-effort, may skip incompatible types):
  python scripts/migrate_sqlite_to_postgres.py --sqlite-url ... --postgres-url ... --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


COPY_ORDER = [
    "users",
    "interview_invites",
    "candidate_verifications",
    "sessions",
    "session_artifacts",
    "identity_verification_attempts",
    "proctor_events",
    "session_review_states",
    "invite_funnel_events",
]

# SQLite stores booleans as 0/1; Postgres Boolean columns need real bools.
_BOOL_COLUMNS: dict[str, frozenset[str]] = {
    "users": frozenset({"is_active", "is_verified"}),
    "sessions": frozenset({"human_review_flag"}),
    "candidate_verifications": frozenset({"verified"}),
    "identity_verification_attempts": frozenset(
        {"verified", "low_identity_confidence"}
    ),
    "session_review_states": frozenset({"human_review_required"}),
}


def _coerce_row(table: str, row: dict) -> dict:
    """Coerce SQLite 0/1 integers to Python bool for known Boolean columns."""
    bool_cols = _BOOL_COLUMNS.get(table)
    if not bool_cols:
        return row
    out = dict(row)
    for col in bool_cols:
        if col in out and isinstance(out[col], int) and not isinstance(out[col], bool):
            out[col] = bool(out[col])
    return out


def _sync_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description="Best-effort SQLite → Postgres copy")
    parser.add_argument("--sqlite-url", required=True)
    parser.add_argument("--postgres-url", required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List tables/row counts only; do not write",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Copy rows (requires empty-or-compatible Postgres tables)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Pass --dry-run (safe) or --execute. Default is refuse.")
        print(__doc__)
        return 2

    from sqlalchemy import create_engine, inspect, text

    src = create_engine(_sync_url(args.sqlite_url))
    dst = create_engine(_sync_url(args.postgres_url))

    src_tables = set(inspect(src).get_table_names())
    print("SQLite tables:", sorted(src_tables))

    with src.connect() as conn:
        for table in COPY_ORDER:
            if table not in src_tables:
                print(f"  skip missing: {table}")
                continue
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"  {table}: {count} rows")

    if args.dry_run:
        print("Dry-run complete. Recommended: bootstrap empty RDS, then --execute only if needed.")
        print("WARNING: JSON/UUID quirks may require manual fixes. Prefer fresh start on free tier.")
        return 0

    # Execute path: insert rows table-by-table using raw SELECT *.
    # This is intentionally conservative and may fail on type mismatches —
    # catch and continue so operators can finish remaining tables manually.
    dst_tables = set(inspect(dst).get_table_names())
    errors: list[str] = []
    with src.connect() as sconn, dst.begin() as dconn:
        for table in COPY_ORDER:
            if table not in src_tables:
                continue
            if table not in dst_tables:
                errors.append(f"{table}: missing on Postgres (run bootstrap_db.py first)")
                continue
            rows = sconn.execute(text(f"SELECT * FROM {table}")).mappings().all()
            if not rows:
                print(f"  {table}: empty")
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join(f":{c}" for c in cols)
            col_list = ", ".join(cols)
            insert_sql = text(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT DO NOTHING"
            )
            try:
                for row in rows:
                    dconn.execute(insert_sql, _coerce_row(table, dict(row)))
                print(f"  {table}: copied {len(rows)} rows")
            except Exception as exc:
                errors.append(f"{table}: {exc}")
                print(f"  {table}: FAILED — {exc}")

    if errors:
        print("Completed with errors:")
        for err in errors:
            print(" ", err)
        return 1
    print("Copy finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
