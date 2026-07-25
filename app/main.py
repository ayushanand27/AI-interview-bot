"""
AI Interview Bot - FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.limiter import limiter
from app.core.exceptions import AppException
from app.api.v1.router import api_router
from app.proctoring.api import mountable_app as proctoring_app
from app.routes.interview_routes import router as interview_router
from app.api.v1.recruiter_assessment import router as recruiter_assessment_router
from app.api.v1.invite import router as invite_router

# Load .env before settings/services read environment variables
load_dotenv()

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create missing DB tables (users, sessions, etc.) on startup."""
    from app.db.session import engine
    from app.db.base import Base
    import app.models.user  # noqa: F401
    import app.db.session_model  # noqa: F401
    import app.db.interview_invite_model  # noqa: F401
    import app.db.candidate_verification_model  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables ready")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Do not warm YOLO here — t3.micro OOMs if MediaPipe + Torch load together at boot.
    # Phone detector loads lazily on first analyze that needs it.

    yield

    await engine.dispose()
    logger.info("Database connections closed")


app = FastAPI(
    title="AI Interview Bot",
    description=(
        "Backend API for AI-powered technical interviews. "
        "Flow: create session → generate questions → get current question → "
        "submit answer → next question → end session."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — only configured frontend origins (see ALLOWED_ORIGINS in .env)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(recruiter_assessment_router, prefix="/api/v1")
app.include_router(invite_router, prefix="/api/v1")
app.include_router(interview_router, prefix="/api/v1")
app.mount("/proctor", proctoring_app)

# Mounted sub-app needs its own limiter state for /proctor/* routes
proctoring_app.state.limiter = limiter
proctoring_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
    )


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok"}


@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {
        "message": "AI Interview Bot API",
        "docs": "/docs",
        "api_prefix": "/api/v1",
    }
