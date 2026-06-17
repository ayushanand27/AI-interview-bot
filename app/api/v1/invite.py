"""Candidate invite link API — validation, registration, identity verification."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
async def register_invite_candidate(
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
async def login_invite_candidate(
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
async def verify_invite_identity(
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
