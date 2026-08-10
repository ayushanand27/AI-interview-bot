"""Candidate invite link API — validation, registration, identity verification."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import (
    IDENTITY_VERIFY_LIMIT,
    INVITE_LOGIN_LIMIT,
    INVITE_REGISTER_LIMIT,
    limiter,
)
from app.db.session import get_db
from app.schemas.common import BaseResponse
from app.schemas.invite import (
    InviteCheckResponse,
    InviteLoginRequest,
    InviteRegisterRequest,
    InviteRegisterResponse,
    InviteVerifyIdentityRequest,
    InviteVerifyIdentityResponse,
)
from app.services.invite_service import InviteService

router = APIRouter(prefix="/invite", tags=["Invite"])


@router.get(
    "/{token}",
    response_model=InviteCheckResponse,
    summary="Validate an interview invite link",
)
async def get_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    service = InviteService(db)
    return await service.check_invite(token)


@router.post(
    "/{token}/register",
    response_model=BaseResponse[InviteRegisterResponse],
    summary="Register candidate details and create interview session",
)
@limiter.limit(INVITE_REGISTER_LIMIT)
async def register_invite_candidate(
    request: Request,
    token: str,
    data: InviteRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    service = InviteService(db)
    result = await service.register_candidate(token, data)
    return BaseResponse(
        success=True,
        message="Registration successful",
        data=result,
    )


@router.post(
    "/{token}/login",
    response_model=BaseResponse[InviteRegisterResponse],
    summary="Log in an existing candidate and attach them to this invite session",
)
@limiter.limit(INVITE_LOGIN_LIMIT)
async def login_invite_candidate(
    request: Request,
    token: str,
    data: InviteLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    service = InviteService(db)
    result = await service.login_candidate(token, data)
    return BaseResponse(
        success=True,
        message="Login successful",
        data=result,
    )


@router.post(
    "/{token}/verify-identity",
    response_model=BaseResponse[InviteVerifyIdentityResponse],
    summary="Verify candidate identity using ID photo and selfie",
)
@limiter.limit(IDENTITY_VERIFY_LIMIT)
async def verify_invite_identity(
    request: Request,
    token: str,
    data: InviteVerifyIdentityRequest,
    db: AsyncSession = Depends(get_db),
):
    service = InviteService(db)
    result = await service.verify_identity(token, data)
    return BaseResponse(
        success=True,
        message=result.message,
        data=result,
    )
