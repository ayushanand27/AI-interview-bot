"""Speech-to-text via OpenAI Whisper API."""

from __future__ import annotations

import io
from pathlib import Path

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

from app.core.config import settings
from app.core.exceptions import AIException

ALLOWED_AUDIO_EXTENSIONS = {".webm", ".mp4", ".wav", ".mpeg", ".mp3", ".m4a", ".ogg", ".oga"}
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # Whisper API limit


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
    """
    Send audio bytes to OpenAI Whisper and return transcribed text.

    Args:
        audio_file: Raw audio bytes (webm, mp4, wav, etc.).
        filename: Filename with extension for the API (affects format detection).
    """
    if not audio_file:
        raise ValueError("Audio file is empty")
    if len(audio_file) > MAX_AUDIO_BYTES:
        raise ValueError("Audio file exceeds 25 MB limit")

    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured")

    ext = _guess_extension(filename, None)
    if not filename.lower().endswith(ext):
        filename = f"recording{ext}"

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    buffer = io.BytesIO(audio_file)
    buffer.name = filename

    try:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
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
        raise ValueError("Could not transcribe any speech from the audio")
    if len(text) > settings.MAX_ANSWER_LENGTH:
        raise ValueError(
            f"Transcribed answer exceeds {settings.MAX_ANSWER_LENGTH} characters. "
            "Please shorten your response or type your answer."
        )
    return text
