"""Operational status — /api/v1/status"""

from fastapi import APIRouter

from app.core.config import settings
from app.proctoring.tracker_provider import is_proctoring_available
from app.services.object_storage import get_object_storage
from app.services.session_persistence import (
    check_database_connected_async,
    count_sessions_async,
)

router = APIRouter(tags=["Status"])


@router.get("/status")
async def api_status() -> dict:
    db_ok = await check_database_connected_async()
    session_count = await count_sessions_async() if db_ok else 0
    storage = get_object_storage()

    return {
        "version": "1.0.0",
        "app_name": settings.APP_NAME,
        "database_connected": db_ok,
        "database_backend": "postgres" if settings.is_postgres else "sqlite",
        "storage_backend": storage.backend,
        "s3_configured": settings.s3_enabled,
        "email_configured": settings.email_configured,
        "smtp_host": settings.SMTP_HOST if settings.email_configured else None,
        "coding_questions_enabled": settings.CODING_QUESTIONS_ENABLED,
        "coding_judge_configured": settings.coding_judge_configured,
        "proctoring_loaded": is_proctoring_available(),
        "total_sessions": session_count,
        "retention_days": {
            "artifacts": settings.ARTIFACT_RETENTION_DAYS,
            "identity": settings.IDENTITY_RETENTION_DAYS,
            "recordings": settings.RECORDING_RETENTION_DAYS,
        },
    }
