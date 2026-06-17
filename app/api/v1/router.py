# app/api/v1/router.py
# Master router — mounts all sub-routers under /api/v1
# main.py imports only this file — add new route groups here

from fastapi import APIRouter
from app.api.v1 import auth
from app.api.v1 import recruiter
from app.api.v1 import status

# All routes in this project are versioned under /api/v1
# Versioning lets us release /api/v2 later without breaking existing clients
api_router = APIRouter(prefix="/api/v1")

# ── Mount route groups ────────────────────────────────────
api_router.include_router(auth.router)
api_router.include_router(recruiter.router)
api_router.include_router(status.router)