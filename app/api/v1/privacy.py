"""Privacy / DSAR endpoints — export and delete/anonymize candidate data."""

import logging

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import (
    AppException,
    ForbiddenException,
    InternalServerException,
    NotFoundException,
)
from app.core.limiter import PRIVACY_LIMIT, limiter
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.dsar_service import (
    anonymize_candidate_data,
    build_export_zip,
    collect_candidate_export,
    recruiter_may_access_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/privacy", tags=["Privacy / DSAR"])


class DsarDeleteRequest(BaseModel):
    confirm: bool = Field(
        ...,
        description="Must be true to proceed with irreversible anonymization.",
    )
    delete_files: bool = Field(
        True,
        description="When true, also delete identity images and recordings from storage.",
    )


class AdminDsarExportRequest(BaseModel):
    email: EmailStr


@router.get("/export")
@limiter.limit(PRIVACY_LIMIT)
async def export_my_data(
    request: Request,
    format: str = Query("json", pattern="^(json|zip)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Candidate (or any authenticated user): export own session metadata."""
    try:
        payload = await collect_candidate_export(db, user=current_user)
        if format == "zip":
            data = build_export_zip(payload)
            return Response(
                content=data,
                media_type="application/zip",
                headers={
                    "Content-Disposition": 'attachment; filename="dsar_export.zip"'
                },
            )
        return payload
    except AppException:
        raise
    except Exception as exc:
        logger.exception("DSAR export failed for user_id=%s", getattr(current_user, "id", None))
        raise InternalServerException(
            "Failed to export your data. Please try again later."
        ) from exc


@router.post("/delete-request")
@limiter.limit(PRIVACY_LIMIT)
async def delete_my_data(
    request: Request,
    body: DsarDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Anonymize the caller's account and related candidate artifacts."""
    if not body.confirm:
        raise ForbiddenException("Set confirm=true to proceed with data deletion.")
    try:
        result = await anonymize_candidate_data(
            db,
            user=current_user,
            delete_files=body.delete_files,
        )
    except AppException:
        raise
    except Exception as exc:
        logger.exception("DSAR delete failed for user_id=%s", getattr(current_user, "id", None))
        raise InternalServerException(
            "Failed to anonymize your data. Please try again later."
        ) from exc
    return {
        **result,
        "success": bool(result.get("success", True)),
        "message": result.get("message")
        or result.get("note")
        or "Delete/anonymize completed.",
    }


@router.post("/admin/export")
@limiter.limit(PRIVACY_LIMIT)
async def admin_export_by_email(
    request: Request,
    body: AdminDsarExportRequest,
    format: str = Query("json", pattern="^(json|zip)$"),
    current_user: User = Depends(require_role(UserRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    """Recruiter: export candidate data when the email is on their invites."""
    email = str(body.email).lower()
    allowed = await recruiter_may_access_email(db, current_user, email)
    if not allowed:
        raise ForbiddenException(
            "No invite verification found for this email under your account."
        )
    try:
        payload = await collect_candidate_export(db, email=email)
    except AppException:
        raise
    except Exception as exc:
        logger.exception("Admin DSAR export failed for email=%s", email)
        raise InternalServerException(
            "Failed to export candidate data. Please try again later."
        ) from exc
    if not payload["sessions"] and not payload["candidate_verifications"]:
        raise NotFoundException("No data found for that email.")
    if format == "zip":
        try:
            data = build_export_zip(payload)
        except AppException:
            raise
        except Exception as exc:
            raise InternalServerException(
                "Failed to package candidate export ZIP."
            ) from exc
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="dsar_{email}.zip"'
            },
        )
    return payload


@router.post("/admin/delete-request")
@limiter.limit(PRIVACY_LIMIT)
async def admin_delete_by_email(
    request: Request,
    body: AdminDsarExportRequest,
    confirm: bool = Query(False),
    delete_files: bool = Query(True),
    current_user: User = Depends(require_role(UserRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    """Recruiter: anonymize invite-linked candidate verification data by email."""
    if not confirm:
        raise ForbiddenException("Pass confirm=true to proceed.")
    email = str(body.email).lower()
    allowed = await recruiter_may_access_email(db, current_user, email)
    if not allowed:
        raise ForbiddenException(
            "No invite verification found for this email under your account."
        )
    try:
        result = await anonymize_candidate_data(
            db,
            email=email,
            delete_files=delete_files,
        )
    except AppException:
        raise
    except Exception as exc:
        logger.exception("Admin DSAR delete failed for email=%s", email)
        raise InternalServerException(
            "Failed to anonymize candidate data. Please try again later."
        ) from exc
    return {
        **result,
        "success": bool(result.get("success", True)),
        "message": result.get("message")
        or result.get("note")
        or f"Anonymized invite-linked data for {email}.",
    }
