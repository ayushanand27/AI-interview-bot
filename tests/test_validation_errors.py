"""Unit tests for ValidationError → JSON-safe HTTP detail."""

from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError, field_validator

from app.utils.validation_errors import serializable_validation_errors


class _Sample(BaseModel):
    question_count: int

    @field_validator("question_count")
    @classmethod
    def validate_question_count(cls, v: int) -> int:
        if v < 2:
            raise ValueError("question_count must be between 2 and 20")
        return v


def test_serializable_validation_errors_are_json_safe():
    try:
        _Sample(question_count=1)
    except ValidationError as exc:
        raw = exc.errors()
        assert isinstance(raw[0].get("ctx", {}).get("error"), ValueError)
        safe = serializable_validation_errors(exc)
        # Must not raise — this is what Starlette uses for HTTPException bodies.
        payload = json.dumps(safe)
        assert "question_count" in payload
        assert "must be between" in payload
        assert "ctx" not in safe[0]
