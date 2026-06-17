# main.py
# Entry point — creates FastAPI app, registers middleware,
# exception handlers, and mounts all routes.
# Run with: uvicorn main:app --reload

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppException
from app.api.v1.router import api_router


# ── Lifespan ──────────────────────────────────────────────
# Runs on startup and shutdown — replaces deprecated @app.on_event
# Creates all DB tables on startup so we don't need to run
# migrations manually during development
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────
    # Import all models so SQLAlchemy knows about every table
    # then create them all in SQLite if they don't exist yet
    from app.db.session import engine
    from app.db.base import Base
    # Ensure DB models are imported so SQLAlchemy knows about all tables
    import app.models.user  # noqa: F401
    import app.db.session_model  # noqa: F401

    async with engine.begin() as conn:
        # create_all only creates tables that don't exist yet
        # safe to run every startup — won't drop existing data
        await conn.run_sync(Base.metadata.create_all)

    print(f"✅ Database tables ready")
    print(f"✅ {settings.APP_NAME} started in {settings.APP_ENV} mode")

    yield  # App runs here

    # ── Shutdown ──────────────────────────────────────────
    await engine.dispose()  # Close all DB connections cleanly
    print("👋 Server shutting down")


# ── App Instance ──────────────────────────────────────────
# docs_url enables Swagger UI at /docs — disable in production
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="AI-Assisted Mock & Proctored Interview Platform API",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)


# ── CORS Middleware ───────────────────────────────────────
# Allows the frontend (Next.js on port 3000) to call this API
# Without this, browsers block cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,     # Allows cookies and auth headers
    allow_methods=["*"],        # Allows GET, POST, PUT, DELETE etc.
    allow_headers=["*"],        # Allows Authorization header for JWT
)


# ── Global Exception Handler ──────────────────────────────
# Catches every AppException raised anywhere in the app
# and converts it to a clean JSON response.
# Without this, unhandled exceptions return ugly 500 errors.
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "status_code": exc.status_code,
            "detail": exc.detail,
        }
    )


# ── Catch-all Exception Handler ───────────────────────────
# Safety net — catches any unexpected Python exception
# and returns a clean 500 instead of exposing stack traces
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "An unexpected error occurred",
            "status_code": 500,
            "detail": str(exc) if settings.DEBUG else None,
        }
    )


# ── Routes ────────────────────────────────────────────────
# Mount all API routes under /api/v1
app.include_router(api_router)


# ── Health Check ──────────────────────────────────────────
# Simple endpoint to confirm server is running
# Used by load balancers and monitoring tools later
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }