"""Recruiter dashboard routes."""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.common import BaseResponse
from app.schemas.recruiter import (
    HumanReviewUpdateRequest,
    RecruiterSessionDetail,
    RecruiterSessionSummary,
)
from app.services.recruiter_service import RecruiterService

router = APIRouter(prefix="/recruiter", tags=["Recruiter"])


@router.get(
    "/sessions",
    response_model=BaseResponse[list[RecruiterSessionSummary]],
    summary="List completed interview sessions",
)
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterService(db)
    sessions = await service.list_completed_sessions()
    return BaseResponse(
        success=True,
        message=f"Found {len(sessions)} completed session(s)",
        data=sessions,
    )


@router.get(
    "/sessions/{session_id}/report",
    summary="Download interview PDF report",
)
async def download_session_report(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterService(db)
    pdf_bytes, filename = await service.get_session_report(session_id)
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
    _current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterService(db)
    detail = await service.get_session_detail(session_id)
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
    _current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterService(db)
    detail = await service.set_human_review_flag(session_id, body.flagged)
    return BaseResponse(
        success=True,
        message="Human review flag updated",
        data=detail,
    )
