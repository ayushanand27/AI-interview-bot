import base64
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Request

from app.core.limiter import PROCTOR_ANALYZE_LIMIT, limiter
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from pydantic import BaseModel

from app.proctoring.session_registry import (
    get_warning_manager,
    remove_warning_manager,
)
from app.proctoring.tracker_provider import (
    ProctoringUnavailableError,
    get_eye_tracker,
)
from app.proctoring.object_detector import (
    ObjectDetectionUnavailableError,
    get_object_detector,
    should_run_object_detection,
    clear_object_detection_schedule,
)
from app.services.session_persistence import update_proctoring_summary

router = APIRouter(tags=["Proctoring"])


class FrameRequest(BaseModel):
    frame_base64: str
    session_id: Optional[str] = "default"


class ResetRequest(BaseModel):
    session_id: Optional[str] = None


class AudioViolationRequest(BaseModel):
    session_id: Optional[str] = "default"
    message: str = "Please maintain a quiet environment"
    violation_type: str = "loud_audio"


class DetectedExtensionItem(BaseModel):
    id: str
    name: str


class VerifyEnvironmentRequest(BaseModel):
    session_id: str
    user_agent: str = ""
    detected_extensions: list[DetectedExtensionItem] = []
    virtual_camera_detected: bool = False
    virtual_camera_uncertain: bool = False
    screen_sharing_active: bool = False
    screen_sharing_capability: bool = False


def _analyze_response(
    *,
    session_id: Optional[str],
    eye_status: str,
    gaze_direction: str,
    confidence: float,
    message: str,
    current_status: str,
    violation_type: Optional[str],
    total_violations: int,
    score_penalty_percent: float,
    alert_message: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "eye_status": eye_status,
        "gaze_direction": gaze_direction,
        "confidence": confidence,
        "message": message,
        "current_status": current_status,
        "violation_type": violation_type,
        "total_violations": total_violations,
        "score_penalty_percent": score_penalty_percent,
        # Immediate UI flash for non-eye hits (e.g. cell phone) while eye_status stays ok.
        "alert_message": alert_message,
        # Legacy fields for older clients
        "warning_count": total_violations,
        "terminated": False,
        "is_currently_violating": current_status == "violation",
        "new_warning": None,
    }


def _persist_proctoring_summary(session_id: Optional[str], summary: dict) -> None:
    if not session_id or session_id == "default":
        return
    try:
        update_proctoring_summary(UUID(str(session_id)), summary)
    except (ValueError, TypeError):
        pass


def _build_analyze_payload(
    session_id: Optional[str],
    eye_status: str,
    gaze_direction: str,
    confidence: float,
    message: str,
    warning_mgr,
    *,
    alert_message: Optional[str] = None,
    force_violation_type: Optional[str] = None,
) -> dict[str, Any]:
    violation_type = force_violation_type
    if violation_type is None and eye_status not in (
        "ok",
        "calibrating",
        "unavailable",
        "error",
    ):
        violation_type = warning_mgr.resolve_violation_type(eye_status, gaze_direction)

    current_status = (
        "ok"
        if eye_status in ("ok", "calibrating", "unavailable", "error")
        and not force_violation_type
        else "violation"
    )
    report = warning_mgr.get_integrity_report()
    return _analyze_response(
        session_id=session_id,
        eye_status=eye_status,
        gaze_direction=gaze_direction,
        confidence=confidence,
        message=message,
        current_status=current_status,
        violation_type=violation_type,
        total_violations=report["total_violations"],
        score_penalty_percent=report["score_penalty_percent"],
        alert_message=alert_message,
    )


@router.get("/")
def root():
    return {"service": "AI Interview Proctoring API", "status": "running"}


@router.post("/analyze")
@limiter.limit(PROCTOR_ANALYZE_LIMIT)
def analyze_frame(request: Request, req: FrameRequest):
    import cv2
    import numpy as np

    warning_mgr = get_warning_manager(req.session_id)

    try:
        img_bytes = base64.b64decode(req.frame_base64)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Could not decode image")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid frame: {exc}") from exc

    try:
        tracker = get_eye_tracker()
    except ProctoringUnavailableError as exc:
        return _build_analyze_payload(
            req.session_id, "unavailable", "unknown", 0.0, str(exc), warning_mgr
        )

    try:
        result = tracker.analyze_frame(frame)
    except Exception as exc:
        return _build_analyze_payload(
            req.session_id,
            "error",
            "unknown",
            0.0,
            f"Proctoring analysis failed: {exc}",
            warning_mgr,
        )

    warning_mgr.process_status(
        status=result["status"],
        reason=result["message"],
        gaze=result["gaze_direction"],
        confidence=result["confidence"],
    )

    phone_alert: Optional[str] = None
    phone_recorded = False
    if should_run_object_detection(req.session_id):
        try:
            detector = get_object_detector()
            phone_hits = detector.detect_cell_phones(frame)
            for hit in phone_hits:
                recorded = warning_mgr.record_client_violation(
                    "prohibited_object_detected",
                    hit["message"],
                )
                if recorded is not None:
                    phone_recorded = True
                    phone_alert = hit["message"]
        except ObjectDetectionUnavailableError as exc:
            import logging

            logging.getLogger(__name__).warning(
                "[proctor] Object detector unavailable: %s", exc
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "[proctor] Object detection failed: %s", exc
            )

    return _build_analyze_payload(
        req.session_id,
        result["status"],
        result["gaze_direction"],
        result["confidence"],
        result["message"],
        warning_mgr,
        alert_message=phone_alert,
        force_violation_type="prohibited_object_detected" if phone_recorded else None,
    )


@router.get("/warnings")
def get_warnings(session_id: Optional[str] = None):
    warning_mgr = get_warning_manager(session_id)
    return warning_mgr.get_integrity_report()


@router.get("/integrity-report")
def integrity_report(session_id: Optional[str] = None):
    warning_mgr = get_warning_manager(session_id)
    return warning_mgr.get_integrity_report()


@router.post("/audio-violation")
def report_audio_violation(body: AudioViolationRequest):
    """Client-reported integrity events (ambient audio, tab switch, etc.)."""
    warning_mgr = get_warning_manager(body.session_id)
    violation = warning_mgr.record_client_violation(
        body.violation_type,
        body.message,
    )
    report = warning_mgr.get_integrity_report()
    return {
        "recorded": violation is not None,
        "session_id": body.session_id,
        "message": body.message,
        "current_status": "violation" if violation else "ok",
        "violation_type": body.violation_type if violation else None,
        "total_violations": report["total_violations"],
        "score_penalty_percent": report["score_penalty_percent"],
        "integrity_level": report["integrity_level"],
    }


@router.post("/verify-environment")
def verify_environment(body: VerifyEnvironmentRequest):
    """
    Pre-interview environment check from the client.
    Logs findings to the session proctoring state and blocks unsafe setups.
    """
    warning_mgr = get_warning_manager(body.session_id)
    warnings: list[str] = []
    block_reasons: list[str] = []

    if body.detected_extensions:
        for ext in body.detected_extensions:
            msg = f"Please disable {ext.name} before continuing"
            block_reasons.append(msg)
            warning_mgr.record_client_violation(
                "recording_extension",
                f"Recording extension detected: {ext.name} ({ext.id})",
            )

    if body.virtual_camera_detected:
        msg = "Virtual camera detected - please use your real webcam"
        block_reasons.append(msg)
        warning_mgr.record_client_violation("virtual_camera", msg)
    elif body.virtual_camera_uncertain:
        msg = (
            "Unusual camera setup detected — flagged for review; "
            "use your real webcam if possible"
        )
        warnings.append(msg)
        warning_mgr.record_client_violation("virtual_camera_suspected", msg)

    if body.screen_sharing_active:
        msg = "Screen sharing is active — stop sharing before starting the interview"
        block_reasons.append(msg)
        warning_mgr.record_client_violation("screen_sharing", msg)
    elif body.screen_sharing_capability:
        warnings.append(
            "Screen capture device detected — do not share your screen during the interview"
        )

    if body.user_agent:
        warnings.append(f"User agent logged: {body.user_agent[:120]}")

    report = warning_mgr.get_integrity_report()
    _persist_proctoring_summary(body.session_id, report)

    allowed = len(block_reasons) == 0
    reason = block_reasons[0] if block_reasons else None
    if len(block_reasons) > 1:
        reason = "; ".join(block_reasons)

    return {
        "allowed": allowed,
        "reason": reason,
        "warnings": warnings,
        "session_id": body.session_id,
        "environment_logged": True,
    }


@router.post("/reset")
def reset_session(body: ResetRequest | None = None):
    session_id = body.session_id if body else None
    removed = remove_warning_manager(session_id)
    clear_object_detection_schedule(session_id)
    if removed is not None:
        _persist_proctoring_summary(session_id, removed.get_integrity_report())

    return {"message": "Session reset successfully", "session_id": session_id}


@router.get("/health")
def health_check():
    return {"status": "healthy", "module": "eye_detection"}


mountable_app = FastAPI(
    title="AI Interview Proctoring API",
    description="Proctoring module — Task 5: Eye Movement Detection",
    version="1.0.0",
)
mountable_app.include_router(router)

app = FastAPI(
    title="AI Interview Proctoring API",
    description="Proctoring module — Task 5: Eye Movement Detection",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/proctor")
