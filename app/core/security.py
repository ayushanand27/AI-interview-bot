# app/core/security.py
# ─────────────────────────────────────────────────────────────
# Two responsibilities:
#   1. Password hashing   → hash_password(), verify_password()
#   2. JWT tokens         → create_access_token(), decode_access_token()
#
# Uses bcrypt directly instead of passlib — passlib is unmaintained
# and has compatibility issues with Python 3.14 + bcrypt 4.x.
# ─────────────────────────────────────────────────────────────

from datetime import datetime, timedelta, timezone
import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedException


# ── Password Hashing ──────────────────────────────────────
def hash_password(plain_password: str) -> str:
    """
    Converts plain text password into a bcrypt hash.
    bcrypt automatically adds a random salt — so the same
    password produces a different hash every time.

    Example:
        hash_password("mypassword123")
        → "$2b$12$EixZaYVK1fsbw1ZfbX3OXe..."

    Called in: auth_service.py during registration.
    """
    # bcrypt requires bytes — encode string to bytes first
    password_bytes = plain_password.encode("utf-8")

    # gensalt() generates a random salt with cost factor 12
    # Cost factor 12 = ~250ms per hash — slow enough to deter
    # brute force, fast enough for normal login use
    salt = bcrypt.gensalt(rounds=12)

    hashed = bcrypt.hashpw(password_bytes, salt)

    # Decode back to string for storing in DB
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Checks if a plain text password matches the stored hash.
    Returns True if match, False if not.

    Called in: auth_service.py during login.
    """
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")

    return bcrypt.checkpw(password_bytes, hashed_bytes)


# ── JWT Token Creation ────────────────────────────────────
def create_access_token(user_id: int, role: str) -> str:
    """
    Creates a signed JWT access token containing user identity.

    Token payload contains:
        sub  → user_id (who this token belongs to)
        role → candidate / recruiter
        exp  → expiry timestamp (auto-checked on decode)
        iat  → issued at timestamp

    Called in: auth_service.py after successful login.
    Returns: JWT string like "eyJhbGci..."
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),    # Subject — always string in JWT
        "role": role,           # Used by require_role() in dependencies
        "exp": expire,          # jose checks this automatically on decode
        "iat": now,             # Issued at
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )


def decode_access_token(token: str) -> dict:
    """
    Decodes and verifies a JWT token.
    Returns the payload dict if valid.

    Automatically checks:
        - Signature not tampered
        - Token not expired

    Raises UnauthorizedException if invalid or expired.
    Called in: dependencies.py → get_current_user()
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload

    except JWTError:
        raise UnauthorizedException("Token is invalid or expired")


def decode_refresh_token(token: str) -> dict:
    """Decode and verify a refresh token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid refresh token")
        return payload
    except JWTError:
        raise UnauthorizedException("Refresh token is invalid or expired")


def create_refresh_token(user_id: int) -> str:
    """
    Creates a longer-lived refresh token (7 days).
    Used to get a new access token without re-login.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=7)

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )