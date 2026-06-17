"""Lazy EyeTracker access with model-file validation (not tied to api routes)."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

_lock = Lock()
_tracker = None
_init_error: str | None = None

MODEL_FILENAME = "face_landmarker.task"


class ProctoringUnavailableError(Exception):
    """Raised when the MediaPipe model is missing or EyeTracker failed to load."""


def get_model_path() -> Path:
    return Path(__file__).resolve().parent / MODEL_FILENAME


def model_file_exists() -> bool:
    return get_model_path().is_file()


def get_init_error() -> str | None:
    return _init_error


def is_proctoring_available() -> bool:
    """True if the model file exists and initialization has not failed."""
    if _init_error:
        return False
    if _tracker is not None:
        return True
    return model_file_exists()


def get_eye_tracker():
    """Return a shared EyeTracker instance, initializing on first successful call."""
    global _tracker, _init_error

    with _lock:
        if _init_error:
            raise ProctoringUnavailableError(_init_error)

        if _tracker is not None:
            return _tracker

        model_path = get_model_path()
        if not model_path.is_file():
            _init_error = (
                f"MediaPipe model not found at {model_path}. "
                "Run: python app/proctoring/download_model.py"
            )
            raise ProctoringUnavailableError(_init_error)

        try:
            from app.proctoring.eye_tracker import EyeTracker

            _tracker = EyeTracker()
            return _tracker
        except Exception as exc:
            _init_error = f"Failed to initialize EyeTracker: {exc}"
            raise ProctoringUnavailableError(_init_error) from exc
