"""Proctoring package — eye tracking and warning management."""

__all__ = ["EyeTracker", "WarningManager"]


def __getattr__(name: str):
    if name == "EyeTracker":
        from app.proctoring.eye_tracker import EyeTracker

        return EyeTracker
    if name == "WarningManager":
        from app.proctoring.warning_manager import WarningManager

        return WarningManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
