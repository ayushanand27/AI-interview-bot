# app/schemas/common.py
# Reusable base response shapes — imported by all other schemas

from pydantic import BaseModel
from typing import Any, Generic, TypeVar

T = TypeVar("T")  # Generic type — allows wrapping any data type


class BaseResponse(BaseModel, Generic[T]):
    """Standard wrapper for every API response in the project."""
    success: bool = True        # Did the request succeed?
    message: str = "Success"    # Human readable status
    data: T | None = None       # Actual response payload


class ErrorResponse(BaseModel):
    """Standard shape for all error responses."""
    success: bool = False
    message: str               # What went wrong
    status_code: int           # HTTP status code
    detail: str | None = None  # Optional extra context