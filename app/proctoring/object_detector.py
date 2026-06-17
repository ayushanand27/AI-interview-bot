"""YOLOv8n prohibited-object detection on proctoring frames.

Uses COCO class "cell phone" only. Smartwatch is not a COCO class and cannot
be detected with this model — use manual proctor review for wearables.

Model: yolov8n.pt (~6 MB), auto-downloads on first run via ultralytics.
For offline deployment, pre-download:
  python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

CELL_PHONE_CONFIDENCE = 0.5
OBJECT_DETECT_INTERVAL_SECONDS = 1.5
MSG_PROHIBITED_OBJECT = "Cell phone detected near candidate — possible cheating aid"

_detector = None
_init_error: str | None = None
_lock = Lock()
_last_run_by_session: dict[str, float] = {}


class ObjectDetectionUnavailableError(Exception):
    """Raised when ultralytics/YOLO failed to load."""


def get_object_detector():
    """Return a shared YOLO detector, initializing on first successful call."""
    global _detector, _init_error

    with _lock:
        if _init_error:
            raise ObjectDetectionUnavailableError(_init_error)
        if _detector is not None:
            return _detector
        try:
            from ultralytics import YOLO

            model = YOLO("yolov8n.pt")
            _detector = ProhibitedObjectDetector(model)
            logger.info("[proctor] YOLOv8n object detector loaded")
            return _detector
        except Exception as exc:
            _init_error = f"Failed to initialize object detector: {exc}"
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
            logger.warning("[proctor] YOLO model has no 'cell phone' class id")

    def detect_cell_phones(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if frame is None or frame.size == 0:
            return []

        results = self._model.predict(
            frame,
            verbose=False,
            conf=CELL_PHONE_CONFIDENCE,
            classes=list(self._cell_phone_ids) if self._cell_phone_ids else None,
        )

        hits: list[dict[str, Any]] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls[0])
                if self._cell_phone_ids and cls_id not in self._cell_phone_ids:
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
