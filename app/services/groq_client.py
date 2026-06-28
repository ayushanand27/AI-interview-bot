"""Shared Groq client — single API key for questions, judging, and transcription."""

from functools import lru_cache

from groq import Groq

from app.core.config import settings


@lru_cache
def get_groq_client() -> Groq:
    if not settings.GROQ_API_KEY.strip():
        raise ValueError("GROQ_API_KEY is not configured")
    return Groq(api_key=settings.GROQ_API_KEY.strip())
