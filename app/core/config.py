# app/core/config.py
# ─────────────────────────────────────────────────────────────
# Central configuration — reads .env and exposes typed settings.
# Every other file imports `settings` from here.
# NEVER import os.getenv() directly anywhere else in the project.
# ─────────────────────────────────────────────────────────────

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All app configuration lives here.
    Values are automatically loaded from the .env file.
    If a required value is missing, the app will crash at startup
    with a clear error — better than crashing mid-request.
    """

    # ── App ───────────────────────────────────────────────
    APP_NAME: str = "AI Interview Platform"
    APP_ENV: str = "development"        # development | production
    DEBUG: bool = False

    # ── Database ──────────────────────────────────────────
    # SQLite for now — change to PostgreSQL URL in production
    # Format: sqlite+aiosqlite:///./filename.db
    DATABASE_URL: str

    # ── Auth ──────────────────────────────────────────────
    SECRET_KEY: str                     # Used to sign JWT tokens
    ALGORITHM: str = "HS256"            # JWT signing algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── OpenAI ────────────────────────────────────────────
    OPENAI_API_KEY: str                 # Required — app won't start without it
    OPENAI_MODEL: str = "gpt-4o"        # Model for question generation / general LLM

    # ── Groq (Judge / Scoring) ───────────────────────────
    GROQ_API_KEY: str                   # Required for LLM judge/evaluator

    # ── Interview flow ────────────────────────────────────
    INTERVIEW_QUESTION_COUNT: int = 5  # Default questions when client omits count
    MAX_ANSWER_LENGTH: int = 2000
    QUESTION_TIMER_SECONDS: int = 180  # Per-question time limit (3 minutes)
    SESSION_IDLE_TIMEOUT_MINUTES: int = 15

    # ── File Upload ───────────────────────────────────────
    UPLOAD_DIR: str = "uploads"         # Local folder for resume/audio files
    MAX_FILE_SIZE_MB: int = 10

    # ── CORS ──────────────────────────────────────────────
    # Comma-separated list of allowed frontend origins
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # ── Email (Gmail SMTP) ────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_EMAIL: str = ""
    SMTP_PASSWORD: str = ""
    FRONTEND_URL: str = "http://localhost:5173"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Accept Render/Heroku postgres:// URLs and use async SQLAlchemy driver."""
        if not isinstance(v, str) or not v:
            return v
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v and "+psycopg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("SMTP_EMAIL", "SMTP_HOST", "FRONTEND_URL")
    @classmethod
    def strip_smtp_strings(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("SMTP_PASSWORD")
    @classmethod
    def normalize_smtp_password(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        # Gmail app passwords are 16 chars; strip edges and remove accidental spaces
        return v.strip().replace(" ", "")

    # ── Pydantic Settings Config ───────────────────────────
    # Tells pydantic-settings to read from .env file
    # extra="ignore" means unknown .env keys won't cause errors
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() == "production"

    def sql_echo(self) -> bool:
        """Log SQL queries only in non-production when DEBUG is enabled."""
        if self.is_production:
            return False
        return self.DEBUG

    def get_allowed_origins(self) -> list[str]:
        """
        Converts the comma-separated ALLOWED_ORIGINS string
        into a Python list for FastAPI's CORS middleware.
        Example: "http://localhost:3000,http://localhost:8000"
                 → ["http://localhost:3000", "http://localhost:8000"]
        """
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]


# ── Singleton pattern ──────────────────────────────────────
# @lru_cache means this function only runs ONCE.
# Every file that calls get_settings() gets the same object.
# This avoids re-reading the .env file on every request.
@lru_cache()
def get_settings() -> Settings:
    return Settings()


# ── Module-level shortcut ──────────────────────────────────
# Import this directly: from app.core.config import settings
settings = get_settings()