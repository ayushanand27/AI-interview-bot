# app/schemas/auth.py
# Request and response shapes for all auth endpoints

from pydantic import BaseModel, EmailStr, field_validator
from app.models.user import UserRole


# ── Register ──────────────────────────────────────────────
class RegisterRequest(BaseModel):
    """Data required to create a new account."""
    full_name: str
    email: EmailStr             # Pydantic validates email format automatically
    password: str
    role: UserRole = UserRole.CANDIDATE  # Defaults to candidate if not provided

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        # Enforce minimum password length at schema level
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        # Strip whitespace and check not empty
        if not v.strip():
            raise ValueError("Full name cannot be empty")
        return v.strip()


# ── Login ─────────────────────────────────────────────────
class LoginRequest(BaseModel):
    """Credentials required to log in."""
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Refresh token body for obtaining a new access token."""
    refresh_token: str


# ── Token Response ────────────────────────────────────────
class TokenResponse(BaseModel):
    """Returned after successful login or register."""
    access_token: str           # JWT token — client stores and sends this
    refresh_token: str          # Used to get new access token when expired
    token_type: str = "bearer"  # Always bearer for JWT


# ── User Response ─────────────────────────────────────────
class UserResponse(BaseModel):
    """Safe user data returned by /me endpoint — no password."""
    id: int
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    is_verified: bool = False

    # Tells Pydantic to read data from SQLAlchemy model attributes
    model_config = {"from_attributes": True}


class EmailRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class MessageResponse(BaseModel):
    message: str
    verification_url: str | None = None
    reset_url: str | None = None


class VerifyEmailResponse(BaseModel):
    success: bool
    message: str


class RegisterResponse(BaseModel):
    """Returned after successful registration."""
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    verification_url: str | None = None