#!/usr/bin/env python3
"""Artifact retention cleanup — default dry-run; pass --execute to delete.

Examples:
  python scripts/cleanup_retention.py
  python scripts/cleanup_retention.py --execute
  ARTIFACT_RETENTION_DAYS=14 python scripts/cleanup_retention.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.retention_service import run_retention_cleanup  # noqa: E402


async def _run(dry_run: bool) -> dict:
    async with AsyncSessionLocal() as db:
        report = await run_retention_cleanup(db, dry_run=dry_run)
        if not dry_run:
            await db.commit()
        return report.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description="Retention cleanup for stored artifacts")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete expired files (default is dry-run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report",
    )
    args = parser.parse_args()
    dry_run = not args.execute
    report = asyncio.run(_run(dry_run=dry_run))

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"[{mode}] scanned={report['scanned_artifacts']} actions={report['action_count']} "
          f"deleted_files={report['deleted_files']} cleared={report['cleared_db_paths']}")
    if report["errors"]:
        print("errors:", report["errors"])
    if args.json:
        print(json.dumps(report, indent=2))
    elif report["actions"][:20]:
        print("Sample actions (up to 20):")
        for action in report["actions"][:20]:
            print(
                f"  - {action['artifact_type']} id={action['artifact_id']} "
                f"path={action['storage_path']} ({action['reason']})"
            )
    if dry_run:
        print("No files deleted. Re-run with --execute to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
