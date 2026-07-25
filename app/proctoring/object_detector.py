"""YOLOv8n prohibited-object detection on proctoring frames.

Uses COCO class "cell phone" only. Smartwatch is not a COCO class and cannot
be detected with this model — use manual proctor review for wearables.

Model: yolov8n.pt (~6 MB), auto-downloads on first run via ultralytics.
For offline deployment, pre-download:
  python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

Tuned for small EC2 (t3.micro): low imgsz, CPU-only, short timeout so analyze
requests stay responsive even when RAM is tight.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Lower than default YOLO 0.5 — webcam phones are often partial / angled.
CELL_PHONE_CONFIDENCE = 0.28
OBJECT_DETECT_INTERVAL_SECONDS = 2.0
YOLO_IMGSZ = 320
YOLO_PREDICT_TIMEOUT_SECONDS = 8.0
MSG_PROHIBITED_OBJECT = "Cell phone detected near candidate — possible cheating aid"

_detector = None
_init_error: str | None = None
_lock = Lock()
_last_run_by_session: dict[str, float] = {}
_predict_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yolo-phone")


class ObjectDetectionUnavailableError(Exception):
    """Raised when ultralytics/YOLO failed to load."""


def _model_path() -> str:
    """Prefer the repo-root yolov8n.pt used in production deploys."""
    root = Path(__file__).resolve().parents[2]
    candidate = root / "yolov8n.pt"
    if candidate.is_file():
        return str(candidate)
    return "yolov8n.pt"


def get_object_detector():
    """Return a shared YOLO detector, initializing on first successful call."""
    global _detector, _init_error

    with _lock:
        if _init_error:
            raise ObjectDetectionUnavailableError(_init_error)
        if _detector is not None:
            return _detector
        try:
            # Keep inference on CPU and limit torch thread blow-up on tiny VMs.
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("MKL_NUM_THREADS", "1")

            from ultralytics import YOLO

            model = YOLO(_model_path())
            _detector = ProhibitedObjectDetector(model)
            logger.info("[proctor] YOLOv8n object detector loaded (%s)", _model_path())
            return _detector
        except Exception as exc:
            _init_error = f"Failed to initialize object detector: {exc}"
            logger.exception("[proctor] %s", _init_error)
            raise ObjectDetectionUnavailableError(_init_error) from exc


def should_run_object_detection(session_id: str | None) -> bool:
    """Throttle object detection to once per OBJECT_DETECT_INTERVAL_SECONDS."""
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


def warmup_object_detector() -> bool:
    """Best-effort model load so the first interview analyze is not cold."""
    try:
        detector = get_object_detector()
        blank = np.zeros((YOLO_IMGSZ, YOLO_IMGSZ, 3), dtype=np.uint8)
        detector.detect_cell_phones(blank)
        return True
    except Exception as exc:
        logger.warning("[proctor] Object detector warmup skipped: %s", exc)
        return False


class ProhibitedObjectDetector:
    """Run YOLO on BGR frames and return high-confidence cell phone hits."""

    def __init__(self, model) -> None:
        self._model = model
        self._cell_phone_ids = {
            idx
            for idx, name in model.names.items()
            if str(name).lower() in {"cell phone", "cell_phone"}
        }
        if not self._cell_phone_ids:
            # COCO class id 67 is "cell phone" for standard YOLOv8n weights.
            self._cell_phone_ids = {67}
            logger.warning("[proctor] YOLO names missing cell phone — using class id 67")

    def detect_cell_phones(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if frame is None or frame.size == 0:
            return []

        def _run() -> list[dict[str, Any]]:
            results = self._model.predict(
                frame,
                verbose=False,
                conf=CELL_PHONE_CONFIDENCE,
                classes=list(self._cell_phone_ids),
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
                    if cls_id not in self._cell_phone_ids:
                        continue
                    confidence = float(box.conf[0])
                    if confidence < CELL_PHONE_CONFIDENCE:
                        continue
                    label = result.names.get(cls_id, "cell phone")
                    hits.append(
                        {
                            "label": label,
                            "confidence": round(confidence, 2),
                            "message": MSG_PROHIBITED_OBJECT,
                        }
                    )
            return hits

        try:
            future = _predict_pool.submit(_run)
            return future.result(timeout=YOLO_PREDICT_TIMEOUT_SECONDS)
        except FuturesTimeout:
            logger.warning(
                "[proctor] YOLO phone detect timed out after %.1fs",
                YOLO_PREDICT_TIMEOUT_SECONDS,
            )
            return []
        except Exception as exc:
            logger.warning("[proctor] YOLO phone detect failed: %s", exc)
            return []
