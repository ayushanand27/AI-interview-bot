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
    RecruiterReviewUpdateRequest,
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
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = RecruiterService(db)
    sessions = await service.list_completed_sessions(current_user.id)
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
        message="Review disposition updated",
        data=detail,
    )
