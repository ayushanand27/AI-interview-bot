"""Schemas for jobs, applications, and live interview rooms."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class CreateJobRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    jd_text: str = Field(..., min_length=20)


class JobSummary(BaseModel):
    token: str
    title: str
    apply_link: str
    created_at: datetime
    application_count: int = 0


class JobDetail(BaseModel):
    """Recruiter-only job view including full JD (for assessment-from-job)."""

    token: str
    title: str
    jd_text: str
    apply_link: str
    created_at: datetime
    application_count: int = 0


class PublicJobInfo(BaseModel):
    token: str
    title: str
    jd_preview: str


class ApplicationSummary(BaseModel):
    id: int
    full_name: str
    email: str
    ats_score: float
    fit_label: str | None = None
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    status: str
    created_at: datetime


class UpdateApplicationStatusRequest(BaseModel):
    status: Literal["new", "shortlisted", "rejected"]


class CreateLiveRoomRequest(BaseModel):
    title: str = Field(default="Live technical interview", max_length=255)
    meet_url: str | None = None
    problem_text: str | None = None
    language: str = "python"
    starter_code: str | None = None
    public_tests: list[dict[str, str]] | None = None
    application_id: int | None = None
    expiry_hours: int = 24


class LiveRoomSummary(BaseModel):
    token: str
    title: str
    meet_url: str | None
    join_link: str
    language: str
    status: str
    expiry_at: datetime
    created_at: datetime
    application_id: int | None = None


class LiveRoomPublic(BaseModel):
    token: str
    title: str
    meet_url: str | None
    problem_text: str
    starter_code: str
    language: str
    public_tests: list[dict[str, Any]]
    status: str
    expiry_at: datetime


class LiveRunTestsRequest(BaseModel):
    language: str = "python"
    source: str
    public_tests: list[dict[str, str]] | None = None


class EndLiveRoomRequest(BaseModel):
    final_code: str | None = None
    notes: list[Any] | None = None


class SendLiveInvitesRequest(BaseModel):
    emails: list[EmailStr] = Field(..., min_length=1)
    message: str | None = None
    candidate_name: str | None = None


class SendLiveInvitesResponse(BaseModel):
    sent: int
    failed: list[str]
    live_link: str
    meet_url: str | None = None
    delivery_note: str | None = None
