"""DSAR helpers — candidate data export and delete/anonymize."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.candidate_verification_model import CandidateVerification
from app.db.evidence_model import IdentityVerificationAttempt, SessionArtifact
from app.db.session_model import Session as DBSession
from app.models.user import User, UserRole
from app.services.object_storage import get_object_storage


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _session_export(row: DBSession) -> dict[str, Any]:
    return {
        "session_id": str(row.session_id),
        "user_id": row.user_id,
        "role_title": row.role_title,
        "experience_level": row.experience_level,
        "topic_focus": row.topic_focus,
        "status": row.status,
        "total_questions": row.total_questions,
        "current_question_index": row.current_question_index,
        "final_score": row.final_score,
        "proctoring_summary": row.proctoring_summary,
        "recording_filename": row.recording_filename,
        "recording_mp4_filename": row.recording_mp4_filename,
        "invite_token": row.invite_token,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        # Omit raw answers/questions text dumps from default JSON; include counts only.
        "question_count": len(row.questions or []),
        "answer_count": len(row.answers or []),
    }


async def collect_candidate_export(
    db: AsyncSession,
    *,
    user: User | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable export for a candidate user and/or email."""
    emails: set[str] = set()
    user_id: int | None = None
    if user is not None:
        user_id = user.id
        emails.add(user.email.lower())
    if email:
        emails.add(email.strip().lower())

    sessions: list[DBSession] = []
    if user_id is not None:
        result = await db.execute(select(DBSession).where(DBSession.user_id == user_id))
        sessions.extend(list(result.scalars().all()))

    verifications: list[CandidateVerification] = []
    if emails:
        result = await db.execute(
            select(CandidateVerification).where(
                func.lower(CandidateVerification.email).in_(list(emails))
            )
        )
        verifications = list(result.scalars().all())
        # Include invite-linked sessions not owned by the user account.
        session_ids: set[UUID] = set()
        for v in verifications:
            if not v.session_id:
                continue
            try:
                session_ids.add(UUID(str(v.session_id)))
            except (TypeError, ValueError):
                continue
        existing = {s.session_id for s in sessions}
        missing = [sid for sid in session_ids if sid not in existing]
        if missing:
            result = await db.execute(
                select(DBSession).where(DBSession.session_id.in_(missing))
            )
            sessions.extend(list(result.scalars().all()))

    session_ids = [s.session_id for s in sessions]
    verification_ids = [v.id for v in verifications]

    artifacts: list[SessionArtifact] = []
    if session_ids or verification_ids:
        clauses = []
        if session_ids:
            clauses.append(SessionArtifact.session_id.in_(session_ids))
        if verification_ids:
            clauses.append(
                SessionArtifact.candidate_verification_id.in_(verification_ids)
            )
        result = await db.execute(select(SessionArtifact).where(or_(*clauses)))
        artifacts = list(result.scalars().all())

    attempts: list[IdentityVerificationAttempt] = []
    if verification_ids:
        result = await db.execute(
            select(IdentityVerificationAttempt).where(
                IdentityVerificationAttempt.candidate_verification_id.in_(
                    verification_ids
                )
            )
        )
        attempts = list(result.scalars().all())

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "subject": {
            "user_id": user_id,
            "email": user.email if user else (email or None),
            "full_name": user.full_name if user else None,
            "role": user.role.value if user else None,
        },
        "sessions": [_session_export(s) for s in sessions],
        "candidate_verifications": [
            {
                "id": v.id,
                "token": v.token,
                "candidate_name": v.candidate_name,
                "email": v.email,
                "phone": v.phone,
                "verified": v.verified,
                "confidence_score": v.confidence_score,
                "session_id": v.session_id,
                "id_document_path": v.id_document_path,
                "selfie_path": v.selfie_path,
                "created_at": _iso(v.created_at),
            }
            for v in verifications
        ],
        "identity_attempts": [
            {
                "id": a.id,
                "token": a.token,
                "session_id": a.session_id,
                "verified": a.verified,
                "confidence_score": a.confidence_score,
                "low_identity_confidence": a.low_identity_confidence,
                "ocr_name": a.ocr_name,
                "ocr_document_number": a.ocr_document_number,
                "message": a.message,
                "created_at": _iso(a.created_at),
            }
            for a in attempts
        ],
        "artifacts": [
            {
                "id": a.id,
                "session_id": str(a.session_id) if a.session_id else None,
                "artifact_type": a.artifact_type,
                "storage_path": a.storage_path,
                "mime_type": a.mime_type,
                "file_size_bytes": a.file_size_bytes,
                "created_at": _iso(a.created_at),
            }
            for a in artifacts
        ],
    }


def build_export_zip(payload: dict[str, Any]) -> bytes:
    """Package export JSON (and note about binary artifacts) into a zip."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "export.json",
            json.dumps(payload, indent=2, default=str),
        )
        zf.writestr(
            "README.txt",
            (
                "SmartSkale DSAR export\n"
                "======================\n"
                "export.json contains session metadata, verification records,\n"
                "identity attempt summaries, and artifact path inventory.\n"
                "Binary files (recordings / ID images) are listed by path;\n"
                "request deletion separately if you also need those removed.\n"
            ),
        )
    return buffer.getvalue()


async def anonymize_candidate_data(
    db: AsyncSession,
    *,
    user: User | None = None,
    email: str | None = None,
    delete_files: bool = True,
) -> dict[str, Any]:
    """Anonymize PII and optionally delete identity/recording files."""
    storage = get_object_storage()
    payload = await collect_candidate_export(db, user=user, email=email)
    deleted_files: list[str] = []
    errors: list[str] = []

    emails: set[str] = set()
    if user is not None:
        emails.add(user.email.lower())
    if email:
        emails.add(email.strip().lower())

    # Delete listed artifact files first.
    if delete_files:
        for artifact in payload.get("artifacts", []):
            path = artifact.get("storage_path")
            if not path:
                continue
            try:
                if storage.delete(path):
                    deleted_files.append(path)
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        for ver in payload.get("candidate_verifications", []):
            for key in ("id_document_path", "selfie_path"):
                path = ver.get(key)
                if path and path not in deleted_files:
                    try:
                        if storage.delete(path):
                            deleted_files.append(path)
                    except Exception as exc:
                        errors.append(f"{path}: {exc}")

        for session in payload.get("sessions", []):
            for key in ("recording_filename", "recording_mp4_filename"):
                path = session.get(key)
                if path and path not in deleted_files:
                    try:
                        if storage.delete(path):
                            deleted_files.append(path)
                    except Exception as exc:
                        errors.append(f"{path}: {exc}")

    # Anonymize verification rows.
    if emails:
        result = await db.execute(
            select(CandidateVerification).where(
                func.lower(CandidateVerification.email).in_(list(emails))
            )
        )
        for ver in result.scalars().all():
            ver.candidate_name = "REDACTED"
            ver.email = f"redacted+{ver.id}@example.invalid"
            ver.phone = ""
            ver.id_document_path = None
            ver.selfie_path = None

    # Clear recording pointers + heavy JSON on owned sessions.
    if user is not None:
        result = await db.execute(
            select(DBSession).where(DBSession.user_id == user.id)
        )
        for row in result.scalars().all():
            row.recording_filename = None
            row.recording_mp4_filename = None
            row.resume_text = None
            row.resume_filename = None
            # Keep scores for recruiter analytics; strip free-text answers.
            row.answers = []
            if row.proctoring_summary and isinstance(row.proctoring_summary, dict):
                summary = dict(row.proctoring_summary)
                summary["dsar_anonymized"] = True
                row.proctoring_summary = summary

        # Soft-deactivate account identity.
        user.full_name = "REDACTED"
        user.email = f"deleted+{user.id}@example.invalid"
        user.is_active = False
        user.verification_token = None
        user.reset_token = None

    # Clear artifact storage_path pointers.
    artifact_ids = [a["id"] for a in payload.get("artifacts", []) if a.get("id")]
    if artifact_ids:
        result = await db.execute(
            select(SessionArtifact).where(SessionArtifact.id.in_(artifact_ids))
        )
        for artifact in result.scalars().all():
            artifact.storage_path = None
            meta = dict(artifact.metadata_json or {})
            meta["dsar_deleted_at"] = datetime.now(timezone.utc).isoformat()
            artifact.metadata_json = meta

    await db.flush()

    note = (
        "PII anonymized; identity images and recordings deleted when present. "
        "Session score metadata may remain for recruiter audit."
    )
    errors = list(errors)
    success = len(errors) == 0
    if not success:
        note = (
            "Anonymization completed with some file-deletion errors. "
            "Database PII was redacted; see errors for storage failures."
        )

    return {
        "success": success,
        "message": note,
        "anonymized_at": datetime.now(timezone.utc).isoformat(),
        "deleted_files": deleted_files,
        "deleted_file_count": len(deleted_files),
        "sessions_touched": len(payload.get("sessions", [])),
        "verifications_touched": len(payload.get("candidate_verifications", [])),
        "errors": errors,
        "note": note,
    }


async def recruiter_may_access_email(
    db: AsyncSession,
    recruiter: User,
    email: str,
) -> bool:
    """Allow recruiter DSAR export when email appears on their invites' verifications."""
    from app.db.interview_invite_model import InterviewInvite

    result = await db.execute(
        select(CandidateVerification.id)
        .join(
            InterviewInvite,
            InterviewInvite.token == CandidateVerification.token,
        )
        .where(
            InterviewInvite.recruiter_id == recruiter.id,
            func.lower(CandidateVerification.email) == email.strip().lower(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
