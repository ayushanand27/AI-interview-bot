"""Per-interview-session WarningManager instances."""

from __future__ import annotations

from threading import Lock
from uuid import UUID

from app.proctoring.warning_manager import WarningManager

_lock = Lock()
_warning_managers: dict[str, WarningManager] = {}


def _session_key(session_id: str | UUID | None) -> str:
    if session_id is None or (isinstance(session_id, str) and not session_id.strip()):
        return "default"
    return str(session_id).strip()


def get_warning_manager(session_id: str | UUID | None) -> WarningManager:
    """Return the WarningManager for this session, creating one if needed."""
    key = _session_key(session_id)
    with _lock:
        if key not in _warning_managers:
            _warning_managers[key] = WarningManager()
        return _warning_managers[key]


def get_proctor_warning_count(session_id: str | UUID | None) -> int:
    """Total recorded violations for a session (0 if none yet)."""
    key = _session_key(session_id)
    with _lock:
        mgr = _warning_managers.get(key)
    return len(mgr.violations) if mgr else 0


def get_proctor_penalty_percent(session_id: str | UUID | None) -> float:
    key = _session_key(session_id)
    with _lock:
        mgr = _warning_managers.get(key)
    return mgr.calculate_score_penalty() if mgr else 0.0


def get_proctor_integrity_report(session_id: str | UUID | None) -> dict:
    return get_warning_manager(session_id).get_integrity_report()


def remove_warning_manager(session_id: str | UUID | None) -> WarningManager | None:
    """Remove and return a session's manager (e.g. on reset)."""
    key = _session_key(session_id)
    with _lock:
        return _warning_managers.pop(key, None)
