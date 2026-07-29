"""Retention cleanup for expired session artifacts and identity images.

Default mode is dry-run (non-destructive). Pass --execute to delete.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.db.candidate_verification_model import CandidateVerification
from app.db.evidence_model import SessionArtifact
from app.db.session_model import Session as DBSession
from app.services.object_storage import get_object_storage

logger = logging.getLogger("app.services.retention")

IDENTITY_TYPES = {
    "identity_id_image",
    "identity_selfie_image",
    "identity_selfie_frame",
}
RECORDING_TYPES = {
    "session_recording_webm",
    "session_recording_mp4",
}


@dataclass
class RetentionAction:
    kind: str
    artifact_id: int | None
    storage_path: str | None
    artifact_type: str | None
    reason: str
    created_at: str | None = None


@dataclass
class RetentionReport:
    dry_run: bool
    scanned_artifacts: int = 0
    actions: list[RetentionAction] = field(default_factory=list)
    deleted_files: int = 0
    cleared_db_paths: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "scanned_artifacts": self.scanned_artifacts,
            "action_count": len(self.actions),
            "deleted_files": self.deleted_files,
            "cleared_db_paths": self.cleared_db_paths,
            "errors": self.errors,
            "actions": [
                {
                    "kind": a.kind,
                    "artifact_id": a.artifact_id,
                    "storage_path": a.storage_path,
                    "artifact_type": a.artifact_type,
                    "reason": a.reason,
                    "created_at": a.created_at,
                }
                for a in self.actions
            ],
        }


def _ttl_for_artifact_type(artifact_type: str) -> int:
    if artifact_type in IDENTITY_TYPES:
        return settings.IDENTITY_RETENTION_DAYS
    if artifact_type in RECORDING_TYPES:
        return settings.RECORDING_RETENTION_DAYS
    return settings.ARTIFACT_RETENTION_DAYS


def _is_expired(created_at: datetime | None, ttl_days: int, now: datetime) -> bool:
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at + timedelta(days=ttl_days) < now


async def run_retention_cleanup(
    db,
    *,
    dry_run: bool = True,
    now: datetime | None = None,
) -> RetentionReport:
    """Scan artifacts and optionally delete expired files + clear storage_path."""
    now = now or datetime.now(timezone.utc)
    report = RetentionReport(dry_run=dry_run)
    storage = get_object_storage()

    result = await db.execute(select(SessionArtifact))
    artifacts = list(result.scalars().all())
    report.scanned_artifacts = len(artifacts)

    for artifact in artifacts:
        ttl = _ttl_for_artifact_type(artifact.artifact_type)
        if not _is_expired(artifact.created_at, ttl, now):
            continue
        if not artifact.storage_path:
            continue

        action = RetentionAction(
            kind="delete_artifact_file",
            artifact_id=artifact.id,
            storage_path=artifact.storage_path,
            artifact_type=artifact.artifact_type,
            reason=f"older than {ttl} days",
            created_at=artifact.created_at.isoformat() if artifact.created_at else None,
        )
        report.actions.append(action)

        if dry_run:
            continue

        try:
            if storage.delete(artifact.storage_path):
                report.deleted_files += 1
            artifact.storage_path = None
            if artifact.metadata_json is None:
                artifact.metadata_json = {}
            meta = dict(artifact.metadata_json)
            meta["retention_deleted_at"] = now.isoformat()
            artifact.metadata_json = meta
            report.cleared_db_paths += 1
        except Exception as exc:
            report.errors.append(f"artifact {artifact.id}: {exc}")

    # Clear recording filenames on sessions whose recording artifacts were purged.
    if not dry_run:
        session_result = await db.execute(select(DBSession))
        for row in session_result.scalars().all():
            for field_name in ("recording_filename", "recording_mp4_filename"):
                filename = getattr(row, field_name, None)
                if not filename:
                    continue
                # If file is gone and session is older than recording TTL, clear pointer.
                if _is_expired(row.created_at, settings.RECORDING_RETENTION_DAYS, now):
                    if not storage.exists(filename):
                        setattr(row, field_name, None)
                        report.cleared_db_paths += 1

        ver_result = await db.execute(select(CandidateVerification))
        for ver in ver_result.scalars().all():
            for field_name in ("id_document_path", "selfie_path"):
                path = getattr(ver, field_name, None)
                if not path:
                    continue
                if _is_expired(ver.created_at, settings.IDENTITY_RETENTION_DAYS, now):
                    if not storage.exists(path):
                        setattr(ver, field_name, None)
                        report.cleared_db_paths += 1

        await db.flush()

    logger.info(
        "Retention %s: scanned=%s actions=%s deleted=%s",
        "dry-run" if dry_run else "execute",
        report.scanned_artifacts,
        len(report.actions),
        report.deleted_files,
    )
    return report
