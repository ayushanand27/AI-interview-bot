"""
Integrity violations with score penalties and optional soft lockout.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

SEVERITY_PENALTIES = {
    "minor": 2.0,
    "moderate": 5.0,
    "severe": 15.0,
    "critical": 30.0,
}

VIOLATION_TYPE_LABELS = {
    "no_face": "Face not detected",
    "multiple_faces": "Multiple faces detected",
    "looking_sideways": "Looking away (sideways)",
    "looking_down": "Looking down",
    "loud_audio": "Loud environment",
    "sustained_noise": "Unusual ambient audio",
    "mic_muted": "Microphone muted or disconnected",
    "mic_silent": "No microphone signal",
    "fullscreen_exit": "Left fullscreen mode",
    "tab_switch": "Switched away from interview window",
    "virtual_camera": "Virtual camera",
    "virtual_camera_suspected": "Unusual camera setup",
    "recording_extension": "Screen recording extension",
    "screen_sharing": "Screen sharing",
    "prohibited_object_detected": "Prohibited object detected (cell phone)",
}


def format_violation_type(violation_type: str) -> str:
    return VIOLATION_TYPE_LABELS.get(
        violation_type,
        violation_type.replace("_", " ").title(),
    )


MAX_PENALTY_PERCENT = 50.0
LOCKOUT_SEVERE_COUNT = 3
LOCKOUT_PENALTY_PERCENT = 40.0


@dataclass
class Violation:
    type: str
    severity: str
    timestamp: float = field(default_factory=time.time)
    penalty_percent: float = 0.0
    message: str = ""
    evidence_metadata: dict[str, Any] | None = None


class WarningManager:
    """Tracks proctoring violations and cumulative score penalties per session."""

    VIOLATION_DURATION_SECONDS = 7.0
    COOLDOWN_SECONDS = 15
    MIN_VIOLATION_CONFIDENCE = 0.6
    NO_FACE_MODERATE_SECONDS = 10.0

    def __init__(self) -> None:
        self.violations: List[Violation] = []
        self._violation_start_time: Optional[float] = None
        self._current_violation_type: Optional[str] = None
        self._current_message: Optional[str] = None
        self._last_violation_recorded_at: Optional[float] = None
        self._last_recorded_by_type: dict[str, float] = {}
        self._multiple_faces_violation_count = 0
        self._looking_down_violation_count = 0
        self._terminated = False

    @property
    def warning_count(self) -> int:
        return len(self.violations)

    @property
    def terminated(self) -> bool:
        return self._terminated

    def is_currently_violating(self) -> bool:
        return self._violation_start_time is not None

    def resolve_violation_type(self, status: str, gaze: str) -> Optional[str]:
        if status == "no_face":
            return "no_face"
        if status == "multiple_faces":
            return "multiple_faces"
        if status == "looking_away":
            if gaze == "down":
                return "looking_down"
            if gaze in ("away", "up"):
                return "looking_sideways"
            return "looking_sideways"
        if status == "looking_down":
            return "looking_down"
        return None

    def _severity_and_penalty(
        self, violation_type: str, streak_seconds: float
    ) -> tuple[str, float]:
        if violation_type == "no_face":
            if streak_seconds < self.NO_FACE_MODERATE_SECONDS:
                return "minor", SEVERITY_PENALTIES["minor"]
            return "moderate", SEVERITY_PENALTIES["moderate"]

        if violation_type == "looking_sideways":
            return "minor", SEVERITY_PENALTIES["minor"]

        if violation_type == "looking_down":
            self._looking_down_violation_count += 1
            if self._looking_down_violation_count >= 2:
                return "moderate", SEVERITY_PENALTIES["moderate"]
            return "minor", SEVERITY_PENALTIES["minor"]

        if violation_type == "multiple_faces":
            self._multiple_faces_violation_count += 1
            if self._multiple_faces_violation_count > 3:
                return "critical", SEVERITY_PENALTIES["critical"]
            return "severe", SEVERITY_PENALTIES["severe"]

        if violation_type in ("loud_audio", "tab_switch", "fullscreen_exit"):
            return "minor", SEVERITY_PENALTIES["minor"]

        if violation_type == "sustained_noise":
            return "moderate", SEVERITY_PENALTIES["moderate"]

        if violation_type in ("mic_muted", "mic_silent"):
            return "moderate", SEVERITY_PENALTIES["moderate"]

        if violation_type == "virtual_camera":
            return "severe", SEVERITY_PENALTIES["severe"]

        if violation_type == "recording_extension":
            return "critical", SEVERITY_PENALTIES["critical"]

        if violation_type == "screen_sharing":
            return "moderate", SEVERITY_PENALTIES["moderate"]

        if violation_type == "virtual_camera_suspected":
            return "minor", SEVERITY_PENALTIES["minor"]

        if violation_type == "prohibited_object_detected":
            return "moderate", SEVERITY_PENALTIES["moderate"]

        return "minor", SEVERITY_PENALTIES["minor"]

    def _check_lockout(self) -> None:
        if self._terminated:
            return
        severe_count = sum(
            1 for v in self.violations if v.severity in ("severe", "critical")
        )
        if (
            severe_count >= LOCKOUT_SEVERE_COUNT
            or self.calculate_score_penalty() >= LOCKOUT_PENALTY_PERCENT
        ):
            self._terminated = True

    def record_client_violation(
        self,
        violation_type: str,
        message: str,
        *,
        evidence_metadata: dict[str, Any] | None = None,
    ) -> Optional[Violation]:
        """Record a client-reported integrity violation (audio, tab switch, etc.)."""
        if self._terminated:
            return None

        now = time.time()
        cooldown = (
            8.0
            if violation_type == "prohibited_object_detected"
            else self.COOLDOWN_SECONDS
        )
        last_same = self._last_recorded_by_type.get(violation_type)
        if last_same is not None and (now - last_same) < cooldown:
            return None

        severity, penalty = self._severity_and_penalty(violation_type, 0.0)
        violation = Violation(
            type=violation_type,
            severity=severity,
            timestamp=now,
            penalty_percent=penalty,
            message=message,
            evidence_metadata=evidence_metadata,
        )
        self.violations.append(violation)
        self._last_violation_recorded_at = now
        self._last_recorded_by_type[violation_type] = now
        self._check_lockout()
        return violation

    def record_loud_audio_violation(
        self,
        message: str = "Please maintain a quiet environment",
    ) -> Optional[Violation]:
        return self.record_client_violation("loud_audio", message)

    def process_status(
        self,
        status: str,
        reason: str,
        gaze: str = "unknown",
        confidence: float = 1.0,
    ) -> Optional[Violation]:
        if self._terminated:
            return None

        if status in ("ok", "calibrating", "unavailable", "error"):
            self._reset_active_violation()
            return None

        violation_type = self.resolve_violation_type(status, gaze)
        if violation_type is None:
            self._reset_active_violation()
            return None

        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            conf = 0.0
        if conf != conf:  # NaN (e.g. poor lighting / bad frame math)
            conf = 0.0
        conf = max(0.0, min(1.0, conf))

        if violation_type not in ("no_face", "multiple_faces", "prohibited_object_detected"):
            if conf < self.MIN_VIOLATION_CONFIDENCE:
                return None

        now = time.time()

        if (
            self._violation_start_time is None
            or self._current_violation_type != violation_type
        ):
            self._violation_start_time = now
            self._current_violation_type = violation_type
            self._current_message = reason

        self._current_message = reason
        elapsed = now - (self._violation_start_time or now)

        if elapsed < self.VIOLATION_DURATION_SECONDS:
            return None

        if (
            self._last_violation_recorded_at is not None
            and (now - self._last_violation_recorded_at) < self.COOLDOWN_SECONDS
        ):
            return None

        severity, penalty = self._severity_and_penalty(violation_type, elapsed)
        violation = Violation(
            type=violation_type,
            severity=severity,
            timestamp=now,
            penalty_percent=penalty,
            message=reason,
        )
        self.violations.append(violation)
        self._last_violation_recorded_at = now
        self._reset_active_violation()
        self._check_lockout()
        return violation

    def calculate_score_penalty(self) -> float:
        total = 0.0
        for v in self.violations:
            try:
                p = float(v.penalty_percent)
            except (TypeError, ValueError):
                continue
            if p != p or p == float("inf") or p == float("-inf"):  # NaN/inf
                continue
            total += max(0.0, p)
        return min(total, MAX_PENALTY_PERCENT)

    def _integrity_level(self, penalty_percent: float) -> str:
        if penalty_percent <= 0:
            return "clean"
        if penalty_percent <= 10:
            return "minor_concerns"
        if penalty_percent <= 25:
            return "moderate_concerns"
        return "serious_concerns"

    def get_integrity_report(self) -> dict:
        penalty = self.calculate_score_penalty()
        return {
            "total_violations": len(self.violations),
            "violations": [
                {
                    "type": v.type,
                    "severity": v.severity,
                    "time": v.timestamp,
                    "penalty_percent": v.penalty_percent,
                    "message": v.message,
                    "evidence_metadata": v.evidence_metadata,
                }
                for v in self.violations
            ],
            "score_penalty_percent": penalty,
            "integrity_level": self._integrity_level(penalty),
            "terminated": self._terminated,
        }

    def get_summary(self) -> dict:
        """Legacy shape for DB persistence and recruiter reports."""
        report = self.get_integrity_report()
        return {
            "warning_count": report["total_violations"],
            "terminated": self._terminated,
            "warnings": [
                {
                    "level": i + 1,
                    "reason": v["message"],
                    "timestamp": v["time"],
                    "gaze": v["type"],
                    "severity": v["severity"],
                    "penalty_percent": v["penalty_percent"],
                }
                for i, v in enumerate(report["violations"])
            ],
            **report,
        }

    def rehydrate_from_summary(self, summary: dict[str, Any] | None) -> None:
        """Restore violations from persisted proctoring_summary after process restart."""
        if not isinstance(summary, dict) or self.violations:
            return
        raw = summary.get("violations") or summary.get("warnings") or []
        if not isinstance(raw, list):
            return
        for item in raw:
            if not isinstance(item, dict):
                continue
            vtype = str(item.get("type") or item.get("gaze") or "unknown")
            severity = str(item.get("severity") or "minor")
            try:
                ts = float(item.get("time") or item.get("timestamp") or time.time())
            except (TypeError, ValueError):
                ts = time.time()
            try:
                penalty = float(item.get("penalty_percent") or 0.0)
            except (TypeError, ValueError):
                penalty = 0.0
            if penalty != penalty or penalty == float("inf") or penalty < 0:
                penalty = 0.0
            penalty = min(penalty, MAX_PENALTY_PERCENT)
            message = str(item.get("message") or item.get("reason") or "")
            evidence = item.get("evidence_metadata")
            self.violations.append(
                Violation(
                    type=vtype,
                    severity=severity,
                    timestamp=ts,
                    penalty_percent=penalty,
                    message=message,
                    evidence_metadata=evidence if isinstance(evidence, dict) else None,
                )
            )
        self._terminated = bool(summary.get("terminated"))
        self._check_lockout()

    def reset(self) -> None:
        self.violations.clear()
        self._reset_active_violation()
        self._last_violation_recorded_at = None
        self._last_recorded_by_type.clear()
        self._multiple_faces_violation_count = 0
        self._looking_down_violation_count = 0
        self._terminated = False

    def _reset_active_violation(self) -> None:
        self._violation_start_time = None
        self._current_violation_type = None
        self._current_message = None
