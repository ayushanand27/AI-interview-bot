# app/api/v1/router.py
# Core router — mounts auth, recruiter, status, and privacy under /api/v1.
# NOTE: invite, jobs, live, and recruiter_assessment are mounted directly
# in app/main.py (not here) to keep this file's import graph simple.

from fastapi import APIRouter
from app.api.v1 import auth
from app.api.v1 import privacy
from app.api.v1 import recruiter
from app.api.v1 import status

# All routes in this project are versioned under /api/v1
# Versioning lets us release /api/v2 later without breaking existing clients
api_router = APIRouter(prefix="/api/v1")

# ── Mount route groups ────────────────────────────────────
api_router.include_router(auth.router)
api_router.include_router(recruiter.router)
api_router.include_router(status.router)
api_router.include_router(privacy.router)
