"""Recruiter dashboard routes."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.common import BaseResponse
from app.schemas.recruiter import (
    HumanReviewUpdateRequest,
    RecruiterAnalyticsResponse,
    RecruiterReviewUpdateRequest,
    RecruiterSessionDetail,
    RecruiterSessionFilters,
    RecruiterSessionSummary,
)
from app.services.recruiter_analytics_service import RecruiterAnalyticsService
from app.services.recruiter_service import RecruiterService

router = APIRouter(prefix="/recruiter", tags=["Recruiter"])


def _parse_filters(
    role_title: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    invite_token: Optional[str] = None,
    score_band: Optional[str] = None,
    integrity_level: Optional[str] = None,
    review_status: Optional[str] = None,
) -> RecruiterSessionFilters:
    return RecruiterSessionFilters(
        role_title=role_title,
        date_from=date_from,
        date_to=date_to,
        invite_token=invite_token,
        score_band=score_band,
        integrity_level=integrity_level,
        review_status=review_status,
    )


@router.get(
    "/sessions",
    response_model=BaseResponse[list[RecruiterSessionSummary]],
    summary="List completed interview sessions",
)
async def list_sessions(
    role_title: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    invite_token: Optional[str] = Query(None),
    score_band: Optional[str] = Query(None),
    integrity_level: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    filters = _parse_filters(
        role_title=role_title,
        date_from=date_from,
        date_to=date_to,
        invite_token=invite_token,
        score_band=score_band,
        integrity_level=integrity_level,
        review_status=review_status,
    )
    has_filters = any(
        [
            role_title,
            date_from,
            date_to,
            invite_token,
            score_band,
            integrity_level,
            review_status,
        ]
    )
    if has_filters:
        analytics = RecruiterAnalyticsService(db)
        sessions = await analytics.list_filtered_sessions(current_user.id, filters)
    else:
        service = RecruiterService(db)
        sessions = await service.list_completed_sessions(current_user.id)
    return BaseResponse(
        success=True,
        message=f"Found {len(sessions)} completed session(s)",
        data=sessions,
    )


@router.get(
    "/analytics",
    response_model=BaseResponse[RecruiterAnalyticsResponse],
    summary="Recruiter analytics dashboard metrics",
)
async def get_analytics(
    role_title: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    invite_token: Optional[str] = Query(None),
    score_band: Optional[str] = Query(None),
    integrity_level: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    filters = _parse_filters(
        role_title=role_title,
        date_from=date_from,
        date_to=date_to,
        invite_token=invite_token,
        score_band=score_band,
        integrity_level=integrity_level,
        review_status=review_status,
    )
    service = RecruiterAnalyticsService(db)
    analytics = await service.get_analytics(current_user.id, filters)
    return BaseResponse(
        success=True,
        message="Analytics generated",
        data=analytics,
    )


@router.get(
    "/sessions/export",
    summary="Export completed sessions as CSV",
)
async def export_sessions_csv(
    role_title: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    invite_token: Optional[str] = Query(None),
    score_band: Optional[str] = Query(None),
    integrity_level: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    filters = _parse_filters(
        role_title=role_title,
        date_from=date_from,
        date_to=date_to,
        invite_token=invite_token,
        score_band=score_band,
        integrity_level=integrity_level,
        review_status=review_status,
    )
    service = RecruiterAnalyticsService(db)
    csv_text, filename = await service.export_sessions_csv(current_user.id, filters)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/assessments/export",
    summary="Export assessment performance as CSV",
)
async def export_assessments_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterAnalyticsService(db)
    csv_text, filename = await service.export_assessments_csv(current_user.id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/sessions/{session_id}/report",
    summary="Download interview PDF report",
)
async def download_session_report(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterService(db)
    pdf_bytes, filename = await service.get_session_report(current_user.id, session_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/sessions/{session_id}",
    response_model=BaseResponse[RecruiterSessionDetail],
    summary="Get full interview transcript with judgments",
)
async def get_session_detail(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterService(db)
    detail = await service.get_session_detail(current_user.id, session_id)
    return BaseResponse(
        success=True,
        message="Session retrieved successfully",
        data=detail,
    )


@router.patch(
    "/sessions/{session_id}/human-review",
    response_model=BaseResponse[RecruiterSessionDetail],
    summary="Mark or clear a session for human review",
)
async def update_human_review(
    session_id: UUID,
    body: HumanReviewUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterService(db)
    detail = await service.set_human_review_flag(
        current_user.id, session_id, body.flagged
    )
    return BaseResponse(
        success=True,
        message="Human review flag updated",
        data=detail,
    )


@router.patch(
    "/sessions/{session_id}/review",
    response_model=BaseResponse[RecruiterSessionDetail],
    summary="Update recruiter review disposition and notes",
)
async def update_review_state(
    session_id: UUID,
    body: RecruiterReviewUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterService(db)
    detail = await service.update_review_state(
        current_user.id,
        session_id,
        body.review_status,
        body.review_notes,
    )
    return BaseResponse(
        success=True,
        message="Review state updated",
        data=detail,
    )
