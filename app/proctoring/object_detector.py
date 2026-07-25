"""YOLOv8n prohibited-object detection on proctoring frames.

Uses COCO class "cell phone" only. Runs YOLO in a dedicated child process so
MediaPipe (EyeTracker) in the API process cannot interfere — required on small
EC2 instances where both models share one Python interpreter unreliably.

Model: yolov8n.pt (~6 MB) at repo root.
"""

from __future__ import annotations

import logging
import os
import time
from multiprocessing import get_context
from pathlib import Path
from threading import Lock
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# spawn avoids inheriting MediaPipe/TFLite state from the API process.
_mp = get_context("spawn")

CELL_PHONE_CONFIDENCE = 0.28
OBJECT_DETECT_INTERVAL_SECONDS = 2.0
YOLO_IMGSZ = 320
WORKER_TIMEOUT_SECONDS = 25.0
MSG_PROHIBITED_OBJECT = "Cell phone detected near candidate — possible cheating aid"

_lock = Lock()
_last_run_by_session: dict[str, float] = {}
_request_q: Any = None
_response_q: Any = None
_worker: Any = None
_init_error: str | None = None
_init_failed_at: float | None = None
INIT_RETRY_SECONDS = 30.0


class ObjectDetectionUnavailableError(Exception):
    """Raised when the YOLO worker failed to start."""


def _model_path() -> str:
    root = Path(__file__).resolve().parents[2]
    candidate = root / "yolov8n.pt"
    if candidate.is_file():
        return str(candidate)
    return "yolov8n.pt"


def _worker_main(request_q: Any, response_q: Any, model_path: str) -> None:
    """Child process: load YOLO once, answer detect jobs forever."""
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    try:
        from ultralytics import YOLO

        model = YOLO(model_path)
        phone_ids = {
            idx
            for idx, name in model.names.items()
            if str(name).lower() in {"cell phone", "cell_phone"}
        } or {67}
        response_q.put({"ok": True, "type": "ready"})
    except Exception as exc:
        response_q.put({"ok": False, "type": "ready", "error": str(exc)})
        return

    while True:
        job = request_q.get()
        if job is None or job.get("type") == "stop":
            break
        if job.get("type") != "detect":
            continue
        try:
            arr = np.frombuffer(job["jpeg"], dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None or frame.size == 0:
                response_q.put({"ok": True, "type": "detect", "hits": []})
                continue
            results = model.predict(
                frame,
                verbose=False,
                conf=CELL_PHONE_CONFIDENCE,
                classes=list(phone_ids),
                imgsz=YOLO_IMGSZ,
                device="cpu",
                max_det=5,
            )
            hits: list[dict[str, Any]] = []
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                for box in boxes:
                    cls_id = int(box.cls[0])
                    if cls_id not in phone_ids:
                        continue
                    confidence = float(box.conf[0])
                    if confidence < CELL_PHONE_CONFIDENCE:
                        continue
                    hits.append(
                        {
                            "label": result.names.get(cls_id, "cell phone"),
                            "confidence": round(confidence, 2),
                            "message": MSG_PROHIBITED_OBJECT,
                        }
                    )
            response_q.put({"ok": True, "type": "detect", "hits": hits})
        except Exception as exc:
            response_q.put({"ok": False, "type": "detect", "error": str(exc), "hits": []})


def _ensure_worker() -> None:
    global _request_q, _response_q, _worker, _init_error, _init_failed_at

    if _worker is not None and _worker.is_alive() and _request_q is not None:
        return

    if _init_error and _init_failed_at is not None:
        if time.time() - _init_failed_at < INIT_RETRY_SECONDS:
            raise ObjectDetectionUnavailableError(_init_error)
        _init_error = None
        _init_failed_at = None

    # Clean up a dead worker
    if _worker is not None:
        try:
            _worker.terminate()
        except Exception:
            pass
        _worker = None

    _request_q = _mp.Queue(maxsize=2)
    _response_q = _mp.Queue(maxsize=2)
    _worker = _mp.Process(
        target=_worker_main,
        args=(_request_q, _response_q, _model_path()),
        name="yolo-phone-worker",
        daemon=True,
    )
    _worker.start()
    try:
        ready = _response_q.get(timeout=WORKER_TIMEOUT_SECONDS)
    except Exception as exc:
        _init_error = f"Object detector worker did not start: {exc}"
        _init_failed_at = time.time()
        raise ObjectDetectionUnavailableError(_init_error) from exc

    if not ready.get("ok"):
        _init_error = f"Failed to initialize object detector: {ready.get('error')}"
        _init_failed_at = time.time()
        print(f"[proctor] {_init_error}", flush=True)
        raise ObjectDetectionUnavailableError(_init_error)

    _init_error = None
    _init_failed_at = None
    print(f"[proctor] YOLOv8n worker ready ({_model_path()})", flush=True)


def get_object_detector():
    """Compatibility shim — ensures the worker is running."""
    with _lock:
        _ensure_worker()
        return ProhibitedObjectDetector()


def should_run_object_detection(session_id: str | None) -> bool:
    if not session_id or session_id == "default":
        return False
    now = time.time()
    last = _last_run_by_session.get(session_id, 0.0)
    if now - last < OBJECT_DETECT_INTERVAL_SECONDS:
        return False
    _last_run_by_session[session_id] = now
    return True


def clear_object_detection_schedule(session_id: str | None) -> None:
    if session_id:
        _last_run_by_session.pop(session_id, None)


def detector_status() -> dict[str, Any]:
    alive = bool(_worker is not None and _worker.is_alive())
    return {
        "loaded": alive,
        "init_error": _init_error,
        "init_failed_at": _init_failed_at,
        "confidence": CELL_PHONE_CONFIDENCE,
        "imgsz": YOLO_IMGSZ,
        "mode": "subprocess",
    }


def warmup_object_detector() -> bool:
    try:
        get_object_detector()
        blank = np.zeros((YOLO_IMGSZ, YOLO_IMGSZ, 3), dtype=np.uint8)
        ProhibitedObjectDetector().detect_cell_phones(blank)
        return True
    except Exception as exc:
        logger.warning("[proctor] Object detector warmup skipped: %s", exc)
        return False


class ProhibitedObjectDetector:
    """Send JPEG frames to the YOLO child process and collect cell-phone hits."""

    def detect_cell_phones(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if frame is None or frame.size == 0:
            return []

        with _lock:
            _ensure_worker()
            assert _request_q is not None and _response_q is not None
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return []
            _request_q.put({"type": "detect", "jpeg": buf.tobytes()})
            try:
                result = _response_q.get(timeout=WORKER_TIMEOUT_SECONDS)
            except Exception as exc:
                print(f"[proctor] YOLO worker timeout/error: {exc}", flush=True)
                return []

        if not result.get("ok", False):
            print(
                f"[proctor] YOLO worker detect failed: {result.get('error')}",
                flush=True,
            )
            return []

        hits = result.get("hits") or []
        if hits:
            print(f"[proctor] cell phone hit(s): {hits}", flush=True)
        return hits
