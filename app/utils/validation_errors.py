"""Helpers for turning Pydantic ValidationError into JSON-safe API details."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError


def serializable_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    """Return ValidationError.errors() without non-JSON-serializable ctx values.

    Pydantic v2 embeds the original exception (e.g. ValueError) under ``ctx.error``.
    Passing that list into ``HTTPException(detail=...)`` makes Starlette's
    ``json.dumps`` raise and turns an intended 422 into a 500.
    """
    return exc.errors(include_context=False, include_url=False)
