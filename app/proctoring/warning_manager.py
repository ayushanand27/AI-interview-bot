"""
Integrity violations with score penalties (no interview termination).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

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


@dataclass
class Violation:
    type: str
    severity: str
    timestamp: float = field(default_factory=time.time)
    penalty_percent: float = 0.0
    message: str = ""


class WarningManager:
    """Tracks proctoring violations and cumulative score penalties per session."""

    # Seconds a condition must persist before recording a violation (was 5.0)
    VIOLATION_DURATION_SECONDS = 7.0
    COOLDOWN_SECONDS = 15
    MIN_VIOLATION_CONFIDENCE = 0.6
    # no_face escalates to moderate after this streak (was 5.0)
    NO_FACE_MODERATE_SECONDS = 10.0

    def __init__(self) -> None:
        self.violations: List[Violation] = []
        self._violation_start_time: Optional[float] = None
        self._current_violation_type: Optional[str] = None
        self._current_message: Optional[str] = None
        self._last_violation_recorded_at: Optional[float] = None
        # Per-type cooldown so loud_audio does not suppress phone detection.
        self._last_recorded_by_type: dict[str, float] = {}
        self._multiple_faces_violation_count = 0
        self._looking_down_violation_count = 0

    @property
    def warning_count(self) -> int:
        """Backward-compatible alias for total recorded violations."""
        return len(self.violations)

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

        if violation_type in ("loud_audio", "tab_switch"):
            return "minor", SEVERITY_PENALTIES["minor"]

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

    def record_client_violation(
        self,
        violation_type: str,
        message: str,
    ) -> Optional[Violation]:
        """Record a client-reported integrity violation (audio, tab switch, etc.)."""
        now = time.time()
        # Phone / object hits get a shorter per-type cooldown so they surface quickly.
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
        )
        self.violations.append(violation)
        self._last_violation_recorded_at = now
        self._last_recorded_by_type[violation_type] = now
        return violation

    def record_loud_audio_violation(
        self,
        message: str = "Please maintain a quiet environment",
    ) -> Optional[Violation]:
        """Record a minor integrity violation from client-side ambient audio monitoring."""
        return self.record_client_violation("loud_audio", message)

    def process_status(
        self,
        status: str,
        reason: str,
        gaze: str = "unknown",
        confidence: float = 1.0,
    ) -> Optional[Violation]:
        if status in ("ok", "calibrating", "unavailable", "error"):
            self._reset_active_violation()
            return None

        violation_type = self.resolve_violation_type(status, gaze)
        if violation_type is None:
            self._reset_active_violation()
            return None

        if violation_type not in ("no_face", "multiple_faces", "prohibited_object_detected"):
            if confidence < self.MIN_VIOLATION_CONFIDENCE:
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
        return violation

    def calculate_score_penalty(self) -> float:
        total = sum(v.penalty_percent for v in self.violations)
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
                }
                for v in self.violations
            ],
            "score_penalty_percent": penalty,
            "integrity_level": self._integrity_level(penalty),
        }

    def get_summary(self) -> dict:
        """Legacy shape for DB persistence and recruiter reports."""
        report = self.get_integrity_report()
        return {
            "warning_count": report["total_violations"],
            "terminated": False,
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

    def reset(self) -> None:
        self.violations.clear()
        self._reset_active_violation()
        self._last_violation_recorded_at = None
        self._multiple_faces_violation_count = 0
        self._looking_down_violation_count = 0

    def _reset_active_violation(self) -> None:
        self._violation_start_time = None
        self._current_violation_type = None
        self._current_message = None
