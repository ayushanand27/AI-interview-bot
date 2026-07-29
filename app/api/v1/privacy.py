"""Privacy / DSAR endpoints — export and delete/anonymize candidate data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import ForbiddenException, NotFoundException
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.dsar_service import (
    anonymize_candidate_data,
    build_export_zip,
    collect_candidate_export,
    recruiter_may_access_email,
)

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
async def export_my_data(
    format: str = Query("json", pattern="^(json|zip)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Candidate (or any authenticated user): export own session metadata."""
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


@router.post("/delete-request")
async def delete_my_data(
    body: DsarDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Anonymize the caller's account and related candidate artifacts."""
    if not body.confirm:
        raise ForbiddenException("Set confirm=true to proceed with data deletion.")
    result = await anonymize_candidate_data(
        db,
        user=current_user,
        delete_files=body.delete_files,
    )
    return {"success": True, **result}


@router.post("/admin/export")
async def admin_export_by_email(
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
    payload = await collect_candidate_export(db, email=email)
    if not payload["sessions"] and not payload["candidate_verifications"]:
        raise NotFoundException("No data found for that email.")
    if format == "zip":
        data = build_export_zip(payload)
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="dsar_{email}.zip"'
            },
        )
    return payload


@router.post("/admin/delete-request")
async def admin_delete_by_email(
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
    result = await anonymize_candidate_data(
        db,
        email=email,
        delete_files=delete_files,
    )
    return {"success": True, **result}
