# app/services/auth_service.py
# All authentication business logic — register, login, get current user

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, UserRole
from app.schemas.auth import RegisterRequest, LoginRequest
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    UnauthorizedException,
    NotFoundException,
)
from app.services.email_service import (
    send_password_reset_email,
    send_verification_email,
)


class AuthService:
    """
    Handles all auth operations.
    Receives a DB session on init — one service instance per request.
    """

    def __init__(self, db: AsyncSession):
        self.db = db  # DB session injected from route via Depends(get_db)

    async def register(self, data: RegisterRequest) -> dict:
        """
        Creates a new user account.
        Steps: check email unique → hash password → save → return tokens.
        """

        # ── Step 1: Check email not already registered ────
        existing = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        if existing.scalar_one_or_none():
            raise ConflictException("Email already registered, please login")

        # ── Step 2: Hash password — never store plain text ─
        hashed = hash_password(data.password)

        # ── Step 3: Create user record ────────────────────
        verification_token = str(uuid4())
        user = User(
            full_name=data.full_name,
            email=data.email,
            hashed_password=hashed,
            role=data.role,
            is_active=True,
            is_verified=False,
            verification_token=verification_token,
            verification_token_expiry=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        self.db.add(user)
        await self.db.flush()   # flush assigns the auto-generated ID without full commit

        send_verification_email(user.email, user.full_name, verification_token)

        # ── Step 4: Generate tokens with new user's ID ────
        access_token = create_access_token(user_id=user.id, role=user.role.value)
        refresh_token = create_refresh_token(user_id=user.id)

        return {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    async def login(self, data: LoginRequest) -> dict:
        """
        Authenticates a user and returns tokens.
        Steps: find user by email → verify password → return tokens.
        """

        # ── Step 1: Find user by email ────────────────────
        result = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        user = result.scalar_one_or_none()

        # Use same error for both "not found" and "wrong password"
        # Never tell the caller which one failed — security best practice
        if not user:
            raise UnauthorizedException("Invalid email or password")

        # ── Step 2: Verify password against stored hash ───
        if not verify_password(data.password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password")

        # ── Step 3: Check account is active ───────────────
        if not user.is_active:
            raise UnauthorizedException("Your account has been deactivated")

        # ── Step 4: Generate and return tokens ────────────
        access_token = create_access_token(user_id=user.id, role=user.role.value)
        refresh_token = create_refresh_token(user_id=user.id)

        return {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    async def refresh(self, refresh_token: str) -> dict:
        """Issue a new access token from a valid refresh token."""
        payload = decode_refresh_token(refresh_token)
        user_id = int(payload["sub"])
        user = await self.get_user_by_id(user_id)
        if not user.is_active:
            raise UnauthorizedException("Your account has been deactivated")

        access_token = create_access_token(user_id=user.id, role=user.role.value)
        new_refresh = create_refresh_token(user_id=user.id)
        return {
            "access_token": access_token,
            "refresh_token": new_refresh,
        }

    async def get_user_by_id(self, user_id: int) -> User:
        """Fetches a single user by ID — used by /me endpoint."""

        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise NotFoundException("User not found")

        return user

    async def verify_email(self, token: str) -> dict:
        result = await self.db.execute(
            select(User).where(User.verification_token == token)
        )
        user = result.scalar_one_or_none()
        if not user:
            return {
                "success": False,
                "message": "Link expired or invalid. Please request a new verification email.",
            }

        now = datetime.now(timezone.utc)
        expiry = user.verification_token_expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry is None or now > expiry:
            return {
                "success": False,
                "message": "Link expired. Please request a new verification email.",
            }

        user.is_verified = True
        user.verification_token = None
        user.verification_token_expiry = None
        return {"success": True, "message": "Email verified successfully"}

    async def forgot_password(self, email: str) -> dict:
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            reset_token = str(uuid4())
            user.reset_token = reset_token
            user.reset_token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            send_password_reset_email(user.email, user.full_name, reset_token)

        return {
            "message": "If this email exists, you will receive a reset link shortly."
        }

    async def reset_password(self, token: str, new_password: str) -> dict:
        if len(new_password) < 8:
            raise BadRequestException("Password must be at least 8 characters")

        result = await self.db.execute(select(User).where(User.reset_token == token))
        user = result.scalar_one_or_none()
        if not user:
            raise BadRequestException("Invalid or expired reset link")

        now = datetime.now(timezone.utc)
        expiry = user.reset_token_expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry is None or now > expiry:
            raise BadRequestException("Invalid or expired reset link")

        user.hashed_password = hash_password(new_password)
        user.reset_token = None
        user.reset_token_expiry = None
        return {
            "message": "Password reset successfully. You can now login with your new password."
        }

    async def resend_verification(self, email: str) -> dict:
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            return {"message": "Verification email sent"}

        if user.is_verified:
            return {"message": "Already verified"}

        verification_token = str(uuid4())
        user.verification_token = verification_token
        user.verification_token_expiry = datetime.now(timezone.utc) + timedelta(hours=24)
        send_verification_email(user.email, user.full_name, verification_token)
        return {"message": "Verification email sent"}