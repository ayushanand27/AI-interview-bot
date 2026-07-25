# app/api/v1/auth.py
# Auth routes — /register, /login, /me
# Routes only: validate input → call service → return response
# No business logic here — that lives in auth_service.py

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

from app.core.limiter import AUTH_LOGIN_LIMIT, AUTH_REGISTER_LIMIT, limiter
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import AppException
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    RegisterResponse,
    TokenResponse,
    UserResponse,
    EmailRequest,
    ResetPasswordRequest,
    MessageResponse,
    VerifyEmailResponse,
)
from app.schemas.common import BaseResponse, ErrorResponse
from app.services.auth_service import AuthService

# ── Router ────────────────────────────────────────────────
# prefix means all routes here start with /auth
# tags groups them under "Auth" in Swagger UI /docs
router = APIRouter(prefix="/auth", tags=["Auth"])


# ── POST /auth/register ───────────────────────────────────
@router.post(
    "/register",
    response_model=BaseResponse[RegisterResponse],
    status_code=201,        # 201 = Created (more accurate than 200 for new resources)
    summary="Register a new account",
)
@limiter.limit(AUTH_REGISTER_LIMIT)
async def register(
    request: Request,
    data: RegisterRequest,              # Pydantic validates the request body
    db: AsyncSession = Depends(get_db), # DB session injected automatically
):
    """
    Creates a new candidate or recruiter account.
    Returns user info + access token + refresh token.
    """
    service = AuthService(db)           # One service instance per request
    result = await service.register(data)

    return BaseResponse(
        success=True,
        message="Account created. Please check your email to verify your account.",
        data=RegisterResponse(
            user=UserResponse.model_validate(result["user"]),
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            verification_url=result.get("verification_url"),
        )
    )


# ── POST /auth/login ──────────────────────────────────────
@router.post(
    "/login",
    response_model=BaseResponse[TokenResponse],
    status_code=200,
    summary="Login with email and password",
)
@limiter.limit(AUTH_LOGIN_LIMIT)
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticates user credentials.
    Returns access token + refresh token on success.
    """
    service = AuthService(db)
    result = await service.login(data)

    return BaseResponse(
        success=True,
        message="Login successful",
        data=TokenResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
        )
    )


# ── POST /auth/refresh ────────────────────────────────────
@router.post(
    "/refresh",
    response_model=BaseResponse[TokenResponse],
    status_code=200,
    summary="Refresh access token",
)
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access token."""
    service = AuthService(db)
    result = await service.refresh(data.refresh_token)

    return BaseResponse(
        success=True,
        message="Token refreshed successfully",
        data=TokenResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
        ),
    )


# ── GET /auth/me ──────────────────────────────────────────
@router.get(
    "/me",
    response_model=BaseResponse[UserResponse],
    status_code=200,
    summary="Get current logged-in user",
)
async def get_me(
    # get_current_user decodes JWT and returns User object
    # if token is missing or invalid it raises 401 automatically
    current_user=Depends(get_current_user),
):
    """
    Returns profile of the currently authenticated user.
    Requires valid Bearer token in Authorization header.
    """
    return BaseResponse(
        success=True,
        message="User retrieved successfully",
        data=UserResponse.model_validate(current_user)
    )


# ── GET /auth/verify-email ────────────────────────────────
@router.get(
    "/verify-email",
    response_model=VerifyEmailResponse,
    status_code=200,
    summary="Verify email address from link",
)
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    token = token.strip()
    result = await db.execute(
        select(User).where(User.verification_token == token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification link",
        )

    expiry = user.verification_token_expiry
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if expiry is None or now > expiry:
        raise HTTPException(
            status_code=400,
            detail="Verification link has expired. Please request a new one.",
        )

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expiry = None
    await db.flush()

    return {"success": True, "message": "Email verified successfully"}


# ── POST /auth/forgot-password ────────────────────────────
@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=200,
    summary="Request a password reset email",
)
@limiter.limit(AUTH_LOGIN_LIMIT)
async def forgot_password(
    request: Request,
    data: EmailRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    result = await service.forgot_password(data.email)
    return MessageResponse(
        message=result["message"],
        reset_url=result.get("reset_url"),
    )


# ── POST /auth/reset-password ─────────────────────────────
@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=200,
    summary="Reset password with token from email",
)
@limiter.limit(AUTH_LOGIN_LIMIT)
async def reset_password(
    request: Request,
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    return await service.reset_password(data.token, data.new_password)


# ── POST /auth/resend-verification ────────────────────────
@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=200,
    summary="Resend email verification link",
)
@limiter.limit(AUTH_LOGIN_LIMIT)
async def resend_verification(
    request: Request,
    data: EmailRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    result = await service.resend_verification(data.email)
    return MessageResponse(
        message=result["message"],
        verification_url=result.get("verification_url"),
    )