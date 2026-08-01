"""Job posting + application + ATS shortlist services."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.db.job_live_models import JobApplication, JobPosting
from app.services.ats_scoring import score_resume_against_jd
from app.services.object_storage import get_object_storage
from app.services.resume_parser import extract_text_from_document


class JobService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_job(
        self, recruiter_id: int, *, title: str, jd_text: str
    ) -> JobPosting:
        title = (title or "").strip()
        jd_text = (jd_text or "").strip()
        if len(title) < 2:
            raise BadRequestException("Job title is required")
        if len(jd_text) < 20:
            raise BadRequestException("Job description must be at least 20 characters")
        now = datetime.now(timezone.utc)
        job = JobPosting(
            token=str(uuid.uuid4()),
            recruiter_id=recruiter_id,
            title=title[:255],
            jd_text=jd_text,
            created_at=now,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def list_jobs(self, recruiter_id: int) -> list[JobPosting]:
        result = await self.db.execute(
            select(JobPosting)
            .where(
                JobPosting.recruiter_id == recruiter_id,
                JobPosting.deleted_at.is_(None),
            )
            .order_by(JobPosting.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_job_by_token(self, token: str) -> JobPosting:
        result = await self.db.execute(
            select(JobPosting).where(JobPosting.token == token)
        )
        job = result.scalar_one_or_none()
        if job is None or job.deleted_at is not None:
            raise NotFoundException("Job not found")
        return job

    async def soft_delete_job(self, recruiter_id: int, token: str) -> None:
        job = await self.get_job_by_token(token)
        if job.recruiter_id != recruiter_id:
            raise NotFoundException("Job not found")
        job.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def apply(
        self,
        token: str,
        *,
        full_name: str,
        email: str,
        resume_bytes: bytes,
        resume_filename: str,
    ) -> JobApplication:
        job = await self.get_job_by_token(token)
        name = (full_name or "").strip()
        mail = (email or "").strip().lower()
        if len(name) < 2:
            raise BadRequestException("Name is required")
        if "@" not in mail:
            raise BadRequestException("Valid email is required")
        try:
            resume_text = extract_text_from_document(resume_bytes, resume_filename)
        except ValueError as exc:
            raise BadRequestException(str(exc)) from exc
        if len(resume_text.strip()) < 40:
            raise BadRequestException("Could not extract enough text from resume")

        detail = score_resume_against_jd(
            resume_text,
            job.jd_text,
            enable_semantic=bool(settings.ATS_ENABLE_SEMANTIC),
        )
        storage_key = f"jobs/{job.token}/resumes/{uuid.uuid4().hex}_{resume_filename[-80:]}"
        try:
            get_object_storage().put_bytes(
                storage_key,
                resume_bytes,
                content_type="application/octet-stream",
            )
        except Exception:
            storage_key = None

        app_row = JobApplication(
            job_id=job.id,
            full_name=name[:255],
            email=mail[:255],
            resume_storage_key=storage_key,
            resume_text=resume_text[:200_000],
            ats_score=float(detail.get("ats_score") or 0),
            ats_detail_json=detail,
            status="new",
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(app_row)
        await self.db.commit()
        await self.db.refresh(app_row)
        return app_row

    async def list_applications(
        self, recruiter_id: int, job_token: str
    ) -> list[JobApplication]:
        job = await self.get_job_by_token(job_token)
        if job.recruiter_id != recruiter_id:
            raise NotFoundException("Job not found")
        result = await self.db.execute(
            select(JobApplication)
            .where(JobApplication.job_id == job.id)
            .order_by(JobApplication.ats_score.desc(), JobApplication.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_application_status(
        self,
        recruiter_id: int,
        application_id: int,
        status: str,
    ) -> JobApplication:
        status = (status or "").strip().lower()
        if status not in {"new", "shortlisted", "rejected"}:
            raise BadRequestException("status must be new, shortlisted, or rejected")
        result = await self.db.execute(
            select(JobApplication, JobPosting)
            .join(JobPosting, JobApplication.job_id == JobPosting.id)
            .where(JobApplication.id == application_id)
        )
        row = result.first()
        if row is None:
            raise NotFoundException("Application not found")
        application, job = row
        if job.recruiter_id != recruiter_id or job.deleted_at is not None:
            raise NotFoundException("Application not found")
        application.status = status
        await self.db.commit()
        await self.db.refresh(application)
        return application

    async def get_application_for_recruiter(
        self, recruiter_id: int, application_id: int
    ) -> tuple[JobApplication, JobPosting]:
        result = await self.db.execute(
            select(JobApplication, JobPosting)
            .join(JobPosting, JobApplication.job_id == JobPosting.id)
            .where(JobApplication.id == application_id)
        )
        row = result.first()
        if row is None:
            raise NotFoundException("Application not found")
        application, job = row
        if job.recruiter_id != recruiter_id or job.deleted_at is not None:
            raise NotFoundException("Application not found")
        return application, job
