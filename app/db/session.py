# app/db/session.py
# ─────────────────────────────────────────────────────────────
# Creates the async database engine and session factory.
# This is the single place where the DB connection is configured.
#
# Engine   = the actual connection to the database file
# Session  = a temporary workspace for one set of DB operations
#
# Flow:
#   Request comes in
#   → get_db() opens a new AsyncSession
#   → service does DB work through the session
#   → session commits and closes when request ends
# ─────────────────────────────────────────────────────────────

import sqlite3

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,           # Async version of SQLAlchemy session
    async_sessionmaker,     # Factory that creates AsyncSession instances
    create_async_engine,    # Creates the async database engine
)
from app.core.config import settings


@event.listens_for(Engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


# ── Engine ────────────────────────────────────────────────
# The engine manages the actual connection to SQLite.
# echo=True logs every SQL query to the terminal in development
# — very useful for debugging, set to False in production.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.sql_echo(),  # Off in production; on when DEBUG=True in dev
    future=True,               # Use SQLAlchemy 2.0 style (always True)
)


# ── Session Factory ───────────────────────────────────────
# AsyncSessionLocal is a factory — calling it creates a new session.
# expire_on_commit=False means objects remain accessible after commit.
# Without this, accessing model attributes after commit would fail.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Dependency function ───────────────────────────────────
# This is the function FastAPI injects into every route that
# needs database access via: db: AsyncSession = Depends(get_db)
#
# It's an async generator:
#   - yields the session to the route handler
#   - after the request finishes, resumes and closes the session
#   - if anything fails, rolls back to prevent corrupt data
async def get_db() -> AsyncSession:
    """
    Provides a database session for a single request.
    Used as a FastAPI dependency — injected into routes.

    Usage in a route:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session               # Hand session to the route
            await session.commit()      # Save changes if no errors
        except Exception:
            await session.rollback()    # Undo changes if error occurred
            raise                       # Re-raise so FastAPI handles it