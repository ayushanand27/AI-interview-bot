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
    APP_NAME: str = "AI Interview Bot"
    APP_ENV: str = "development"        # development | production
    DEBUG: bool = False

    # ── Database ──────────────────────────────────────────
    # Local/dev: sqlite+aiosqlite:///./interview_bot.db
    # Docker Postgres: postgresql+asyncpg://interview:interview@127.0.0.1:5433/interview_bot
    # RDS free tier: postgresql+asyncpg://USER:PASS@HOST:5432/interview_bot
    DATABASE_URL: str

    # ── Auth ──────────────────────────────────────────────
    SECRET_KEY: str                     # Used to sign JWT tokens
    ALGORITHM: str = "HS256"            # JWT signing algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── OpenAI (optional legacy) ──────────────────────────
    OPENAI_API_KEY: str = ""            # Optional — not required when using Groq
    OPENAI_MODEL: str = "gpt-4o"

    # ── Groq (questions, judging, transcription) ────────
    GROQ_API_KEY: str
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"

    # ── Interview flow ────────────────────────────────────
    INTERVIEW_QUESTION_COUNT: int = 5  # Default questions when client omits count
    MAX_ANSWER_LENGTH: int = 2000
    QUESTION_TIMER_SECONDS: int = 180  # Per-question time limit (3 minutes)
    SESSION_IDLE_TIMEOUT_MINUTES: int = 15
    # Phase 5 adaptive interviewing (open AI interviews only; invites stay fixed)
    ADAPTIVE_INTERVIEW_ENABLED: bool = True
    ADAPTIVE_QUALITY_LOW: float = 55.0
    ADAPTIVE_QUALITY_HIGH: float = 80.0

    # ── File Upload ───────────────────────────────────────
    UPLOAD_DIR: str = "uploads"         # Local folder / S3 download cache
    MAX_FILE_SIZE_MB: int = 10

    # ── Object storage (optional S3) ───────────────────────
    # When S3_BUCKET + AWS credentials are set, uploads also go to S3.
    # Without them, storage falls back to UPLOAD_DIR (backward compatible).
    S3_BUCKET: str = ""
    S3_PREFIX: str = "interview-bot"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"

    # ── Retention (days) — used by cleanup job ────────────
    ARTIFACT_RETENTION_DAYS: int = 90
    IDENTITY_RETENTION_DAYS: int = 30
    RECORDING_RETENTION_DAYS: int = 60

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

    @property
    def is_postgres(self) -> bool:
        url = (self.DATABASE_URL or "").lower()
        return url.startswith("postgres") or "postgresql" in url.split(":", 1)[0]

    @property
    def is_sqlite(self) -> bool:
        return (self.DATABASE_URL or "").lower().startswith("sqlite")

    @property
    def s3_enabled(self) -> bool:
        """True when bucket and credentials are present — otherwise local disk only."""
        return bool(
            self.S3_BUCKET.strip()
            and self.AWS_ACCESS_KEY_ID.strip()
            and self.AWS_SECRET_ACCESS_KEY.strip()
        )

    @property
    def effective_frontend_url(self) -> str:
        """Frontend base URL for email links — loopback in local dev."""
        url = self.FRONTEND_URL.rstrip("/")
        if not self.is_production:
            return "http://127.0.0.1:5173"
        return url

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