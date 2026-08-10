"""Recruiter job postings + public apply + ATS shortlist APIs."""

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.limiter import JOB_APPLY_LIMIT, RECRUITER_WRITE_LIMIT, limiter
from app.db.job_live_models import JobApplication
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.common import BaseResponse
from app.schemas.jobs_live import (
    ApplicationSummary,
    CreateJobRequest,
    JobDetail,
    JobSummary,
    PublicJobInfo,
    UpdateApplicationStatusRequest,
)
from app.services.job_service import JobService
from app.utils.file_validation import validate_document_upload

router = APIRouter(prefix="/jobs", tags=["Jobs & ATS"])


def _apply_link(token: str) -> str:
    return f"/apply/{token}"


@router.post("", response_model=BaseResponse[JobSummary])
@limiter.limit(RECRUITER_WRITE_LIMIT)
async def create_job(
    request: Request,
    body: CreateJobRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = JobService(db)
    job = await service.create_job(
        current_user.id, title=body.title, jd_text=body.jd_text
    )
    return BaseResponse(
        success=True,
        message="Job created",
        data=JobSummary(
            token=job.token,
            title=job.title,
            apply_link=_apply_link(job.token),
            created_at=job.created_at,
            application_count=0,
        ),
    )


@router.get("", response_model=BaseResponse[list[JobSummary]])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = JobService(db)
    jobs = await service.list_jobs(current_user.id)
    out: list[JobSummary] = []
    for job in jobs:
        count = await db.scalar(
            select(func.count())
            .select_from(JobApplication)
            .where(JobApplication.job_id == job.id)
        )
        out.append(
            JobSummary(
                token=job.token,
                title=job.title,
                apply_link=_apply_link(job.token),
                created_at=job.created_at,
                application_count=int(count or 0),
            )
        )
    return BaseResponse(success=True, message="OK", data=out)


@router.get("/public/{token}", response_model=BaseResponse[PublicJobInfo])
async def public_job(token: str, db: AsyncSession = Depends(get_db)):
    job = await JobService(db).get_job_by_token(token)
    preview = job.jd_text.strip()
    if len(preview) > 1200:
        preview = preview[:1200] + "…"
    return BaseResponse(
        success=True,
        message="OK",
        data=PublicJobInfo(token=job.token, title=job.title, jd_preview=preview),
    )


@router.post("/public/{token}/apply", response_model=BaseResponse[dict])
@limiter.limit(JOB_APPLY_LIMIT)
async def apply_to_job(
    request: Request,
    token: str,
    full_name: str = Form(...),
    email: str = Form(...),
    resume: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not resume.filename:
        raise BadRequestException("Resume file is required")
    raw = await resume.read()
    validate_document_upload(
        raw, content_type=resume.content_type, filename=resume.filename
    )
    app_row = await JobService(db).apply(
        token,
        full_name=full_name,
        email=email,
        resume_bytes=raw,
        resume_filename=resume.filename,
    )
    detail = app_row.ats_detail_json or {}
    return BaseResponse(
        success=True,
        message="Application submitted",
        data={
            "application_id": app_row.id,
            "ats_score": app_row.ats_score,
            "fit_label": detail.get("fit_label"),
            "matched_skills": detail.get("matched_skills") or [],
            "missing_skills": detail.get("missing_skills") or [],
        },
    )


@router.get(
    "/{token}/applications",
    response_model=BaseResponse[list[ApplicationSummary]],
)
async def list_applications(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    rows = await JobService(db).list_applications(current_user.id, token)
    data = [
        ApplicationSummary(
            id=row.id,
            full_name=row.full_name,
            email=row.email,
            ats_score=row.ats_score,
            fit_label=(row.ats_detail_json or {}).get("fit_label"),
            matched_skills=(row.ats_detail_json or {}).get("matched_skills") or [],
            missing_skills=(row.ats_detail_json or {}).get("missing_skills") or [],
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return BaseResponse(success=True, message="OK", data=data)


@router.patch(
    "/applications/{application_id}",
    response_model=BaseResponse[ApplicationSummary],
)
async def update_application_status(
    application_id: int,
    body: UpdateApplicationStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    row = await JobService(db).update_application_status(
        current_user.id, application_id, body.status
    )
    detail = row.ats_detail_json or {}
    return BaseResponse(
        success=True,
        message="Updated",
        data=ApplicationSummary(
            id=row.id,
            full_name=row.full_name,
            email=row.email,
            ats_score=row.ats_score,
            fit_label=detail.get("fit_label"),
            matched_skills=detail.get("matched_skills") or [],
            missing_skills=detail.get("missing_skills") or [],
            status=row.status,
            created_at=row.created_at,
        ),
    )


@router.get("/{token}", response_model=BaseResponse[JobDetail])
async def get_job(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    """Recruiter job detail with full JD — used to create assessments from a job."""
    service = JobService(db)
    job = await service.get_job_by_token(token)
    if job.recruiter_id != current_user.id:
        raise NotFoundException("Job not found")
    count = await db.scalar(
        select(func.count())
        .select_from(JobApplication)
        .where(JobApplication.job_id == job.id)
    )
    return BaseResponse(
        success=True,
        message="OK",
        data=JobDetail(
            token=job.token,
            title=job.title,
            jd_text=job.jd_text,
            apply_link=_apply_link(job.token),
            created_at=job.created_at,
            application_count=int(count or 0),
        ),
    )


@router.delete("/{token}", response_model=BaseResponse[None])
async def delete_job(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    await JobService(db).soft_delete_job(current_user.id, token)
    return BaseResponse(success=True, message="Job deleted", data=None)
