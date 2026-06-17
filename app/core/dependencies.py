# app/core/dependencies.py
# ─────────────────────────────────────────────────────────────
# FastAPI dependency functions injected into routes.
# Two main dependencies:
#   1. get_db()           → provides DB session (from session.py)
#   2. get_current_user() → decodes JWT, returns logged-in user
#
# Usage in any route:
#   db: AsyncSession = Depends(get_db)
#   current_user: User = Depends(get_current_user)
# ─────────────────────────────────────────────────────────────

from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedException, NotFoundException
from app.db.session import get_db
from app.models.session import InterviewSession


# ── OAuth2 Scheme ─────────────────────────────────────────
# Tells FastAPI where to find the token in the request.
# tokenUrl is the login endpoint that issues the token.
# When a route uses this, FastAPI automatically adds
# an "Authorize" button in the Swagger UI (/docs).
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# HTTPBearer shows a proper "Value" field in Swagger instead of username/password form
http_bearer = HTTPBearer()


# ── get_current_user ──────────────────────────────────────
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
    db: AsyncSession = Depends(get_db),
):

# async def get_current_user(
#     token: str = Depends(oauth2_scheme),    # Extracts Bearer token from header
#     db: AsyncSession = Depends(get_db),     # Gets DB session
# ):
    """
    Decodes the JWT token and returns the currently logged-in user.

    Flow:
        1. OAuth2PasswordBearer extracts token from Authorization header
        2. We decode the token using SECRET_KEY
        3. We extract the user_id from the token payload
        4. We fetch the user from the database
        5. We return the User object to the route

    Raises UnauthorizedException if:
        - No token provided
        - Token is expired
        - Token signature is invalid
        - User no longer exists in DB
    """

    # ── Step 1: Decode the JWT token ──────────────────────
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        # Extract user_id from token payload
        # "sub" (subject) is the standard JWT field for user identity
        user_id: str | None = payload.get("sub")

        if user_id is None:
            raise UnauthorizedException("Invalid token — no subject found")

    except JWTError:
        # Covers expired tokens, invalid signature, malformed tokens
        raise UnauthorizedException("Token is invalid or expired")

    # ── Step 2: Fetch user from database ──────────────────
    # Import here to avoid circular imports
    # (models import Base from db, dependencies imports models)
    from app.models.user import User

    result = await db.execute(
        select(User).where(User.id == int(user_id))
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Token was valid but user was deleted after token was issued
        raise NotFoundException("User no longer exists")

    if not user.is_active:
        # User exists but has been deactivated
        raise UnauthorizedException("Account is deactivated")

    return user


# ── get_current_active_user ───────────────────────────────
async def get_current_active_user(
    current_user=Depends(get_current_user),
):
    """
    Shortcut dependency — same as get_current_user but
    makes the intent explicit in route definitions.

    Use this for routes that need a verified active user:
        current_user = Depends(get_current_active_user)
    """
    return current_user


# ── Role-based access ─────────────────────────────────────
def require_role(required_role: str):
    """
    Factory function that returns a dependency checking user role.
    Use this to restrict routes to specific roles.

    Usage:
        @router.get("/recruiter/dashboard")
        async def dashboard(
            current_user = Depends(require_role("recruiter"))
        ):

    Raises ForbiddenException if user doesn't have required role.
    """
    from app.core.exceptions import ForbiddenException

    async def role_checker(current_user=Depends(get_current_user)):
        required = (
            required_role.value
            if hasattr(required_role, "value")
            else str(required_role)
        )
        if current_user.role.value != required:
            raise ForbiddenException(
                f"This action requires '{required}' role"
            )
        return current_user

    return role_checker


# ── Session ownership (candidate recording / report) ───────
async def get_session_owner(
    session_id: UUID,
    db: AsyncSession,
    current_user=None,
    token: str | None = None,
) -> InterviewSession:
    """
    Verify the caller may access a session's candidate-only resources.

    Authorized when:
      1. current_user is set and session.user_id matches, or
      2. token is set and candidate_verifications links token + session_id.
    """
    from app.db.candidate_verification_model import CandidateVerification
    from app.services.session_store import session_store

    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if current_user is not None and session.user_id == current_user.id:
        return session

    if token is not None:
        result = await db.execute(
            select(CandidateVerification).where(
                CandidateVerification.token == token,
                CandidateVerification.session_id == str(session_id),
            )
        )
        if result.scalar_one_or_none() is not None:
            return session

    raise HTTPException(status_code=403, detail="Forbidden")