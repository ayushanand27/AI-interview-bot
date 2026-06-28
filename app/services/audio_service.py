"""Speech-to-text via Groq Whisper API."""

from __future__ import annotations

import io
from pathlib import Path

from groq import APIConnectionError, APIError, RateLimitError

from app.core.config import settings
from app.core.exceptions import AIException
from app.services.groq_client import get_groq_client

ALLOWED_AUDIO_EXTENSIONS = {".webm", ".mp4", ".wav", ".mpeg", ".mp3", ".m4a", ".ogg", ".oga"}
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # API limit


def _guess_extension(filename: str | None, content_type: str | None) -> str:
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in ALLOWED_AUDIO_EXTENSIONS:
            return ext
    if content_type:
        mapping = {
            "audio/webm": ".webm",
            "video/webm": ".webm",
            "audio/mp4": ".mp4",
            "video/mp4": ".mp4",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/ogg": ".ogg",
        }
        if content_type in mapping:
            return mapping[content_type]
    return ".webm"


def transcribe_audio(audio_file: bytes, filename: str = "audio.webm") -> str:
    """Send audio bytes to Groq Whisper and return transcribed text."""
    if not audio_file:
        raise ValueError("Audio file is empty")
    if len(audio_file) > MAX_AUDIO_BYTES:
        raise ValueError("Audio file exceeds 25 MB limit")

    if not settings.GROQ_API_KEY.strip():
        raise ValueError("GROQ_API_KEY is not configured")

    ext = _guess_extension(filename, None)
    if not filename.lower().endswith(ext):
        filename = f"recording{ext}"

    buffer = io.BytesIO(audio_file)
    buffer.name = filename

    try:
        transcription = get_groq_client().audio.transcriptions.create(
            model=settings.GROQ_WHISPER_MODEL,
            file=buffer,
        )
    except (RateLimitError, APIConnectionError, APIError) as exc:
        raise AIException(
            "Audio transcription is temporarily unavailable. Please type your answer instead."
        ) from exc
    except Exception as exc:
        raise AIException(
            "Audio transcription failed. Please type your answer instead."
        ) from exc

    text = (transcription.text or "").strip()
    if not text:
        raise AIException(
            "Could not transcribe audio. Please speak clearly or type your answer."
        )

    if len(text) > settings.MAX_ANSWER_LENGTH:
        raise AIException(
            f"Transcribed answer exceeds {settings.MAX_ANSWER_LENGTH} characters. "
            "Please shorten your response."
        )

    return text
