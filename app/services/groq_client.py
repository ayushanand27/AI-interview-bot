"""Shared Groq client — single API key for questions, judging, and transcription."""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

from groq import APIConnectionError, APIError, APITimeoutError, Groq, RateLimitError

from app.core.config import settings
from app.core.exceptions import AIException

logger = logging.getLogger(__name__)

# One automatic retry after a short pause for rate limits only.
_RATE_LIMIT_RETRY_SLEEP_SEC = 1.5
_DEFAULT_TIMEOUT_SEC = 60.0


@lru_cache
def get_groq_client() -> Groq:
    if not settings.GROQ_API_KEY.strip():
        raise ValueError("GROQ_API_KEY is not configured")
    return Groq(api_key=settings.GROQ_API_KEY.strip())


def groq_chat_completion(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    timeout: float = _DEFAULT_TIMEOUT_SEC,
) -> Any:
    """
    Call Groq chat completions with a timeout and one retry on rate limit.

    Raises AIException with a clear user-facing message on failure.
    """
    if not settings.GROQ_API_KEY.strip():
        raise AIException(
            "Question generation is not configured. Please try again later."
        )

    client = get_groq_client()
    last_exc: Exception | None = None

    for attempt in range(2):
        try:
            return client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
                timeout=timeout,
            )
        except RateLimitError as exc:
            last_exc = exc
            if attempt == 0:
                logger.warning(
                    "Groq rate limit hit; retrying once after %.1fs",
                    _RATE_LIMIT_RETRY_SLEEP_SEC,
                )
                time.sleep(_RATE_LIMIT_RETRY_SLEEP_SEC)
                continue
            raise AIException(
                "Generation failed due to rate limits. Please try again in a moment."
            ) from exc
        except APITimeoutError as exc:
            raise AIException(
                "Generation timed out. Please try again."
            ) from exc
        except (APIConnectionError, APIError) as exc:
            raise AIException(
                "Generation failed. Please try again."
            ) from exc
        except AIException:
            raise
        except Exception as exc:
            raise AIException(
                "Generation failed. Please try again."
            ) from exc

    raise AIException("Generation failed. Please try again.") from last_exc
