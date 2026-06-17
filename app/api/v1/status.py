"""Operational status — /api/v1/status"""

from fastapi import APIRouter

from app.core.config import settings
from app.proctoring.tracker_provider import is_proctoring_available
from app.services.session_persistence import (
    check_database_connected_async,
    count_sessions_async,
)

router = APIRouter(tags=["Status"])


@router.get("/status")
async def api_status() -> dict:
    db_ok = await check_database_connected_async()
    session_count = await count_sessions_async() if db_ok else 0

    return {
        "version": "1.0.0",
        "app_name": settings.APP_NAME,
        "database_connected": db_ok,
        "proctoring_loaded": is_proctoring_available(),
        "total_sessions": session_count,
    }
