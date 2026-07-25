"""YOLOv8n prohibited-object detection on proctoring frames.

Uses COCO class "cell phone" only. Runs YOLO in a dedicated subprocess
(`python -m app.proctoring.yolo_phone_service`) so MediaPipe EyeTracker in the
API process cannot interfere.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Lock
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

CELL_PHONE_CONFIDENCE = 0.28
OBJECT_DETECT_INTERVAL_SECONDS = 2.0
YOLO_IMGSZ = 320
WORKER_START_TIMEOUT_SECONDS = 60.0
WORKER_DETECT_TIMEOUT_SECONDS = 30.0
MSG_PROHIBITED_OBJECT = "Cell phone detected near candidate — possible cheating aid"

_lock = Lock()
_last_run_by_session: dict[str, float] = {}
_proc: subprocess.Popen[str] | None = None
_init_error: str | None = None
_init_failed_at: float | None = None
INIT_RETRY_SECONDS = 30.0


class ObjectDetectionUnavailableError(Exception):
    """Raised when the YOLO worker failed to start."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_worker() -> None:
    global _proc, _init_error, _init_failed_at

    if _proc is not None and _proc.poll() is None:
        return

    if _init_error and _init_failed_at is not None:
        if time.time() - _init_failed_at < INIT_RETRY_SECONDS:
            raise ObjectDetectionUnavailableError(_init_error)
        _init_error = None
        _init_failed_at = None

    if _proc is not None:
        try:
            _proc.kill()
        except Exception:
            pass
        _proc = None

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = ""
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["PYTHONPATH"] = str(_repo_root()) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    try:
        _proc = subprocess.Popen(
            [sys.executable, "-m", "app.proctoring.yolo_phone_service"],
            cwd=str(_repo_root()),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        assert _proc.stdout is not None
        deadline = time.time() + WORKER_START_TIMEOUT_SECONDS
        ready = False
        while time.time() < deadline:
            line = _proc.stdout.readline()
            if not line:
                if _proc.poll() is not None:
                    break
                continue
            if line.strip() == "READY":
                ready = True
                break
        if not ready:
            _init_error = "Object detector worker did not become READY"
            _init_failed_at = time.time()
            raise ObjectDetectionUnavailableError(_init_error)
    except ObjectDetectionUnavailableError:
        raise
    except Exception as exc:
        _init_error = f"Failed to start object detector worker: {exc}"
        _init_failed_at = time.time()
        raise ObjectDetectionUnavailableError(_init_error) from exc

    _init_error = None
    _init_failed_at = None
    print("[proctor] YOLOv8n phone service READY", flush=True)


def get_object_detector():
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
    alive = bool(_proc is not None and _proc.poll() is None)
    return {
        "loaded": alive,
        "init_error": _init_error,
        "init_failed_at": _init_failed_at,
        "confidence": CELL_PHONE_CONFIDENCE,
        "imgsz": YOLO_IMGSZ,
        "mode": "subprocess-service",
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
    """Send frames to the YOLO subprocess and collect cell-phone hits."""

    def detect_cell_phones(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if frame is None or frame.size == 0:
            return []

        with _lock:
            _ensure_worker()
            assert _proc is not None and _proc.stdin and _proc.stdout
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return []
            payload = base64.b64encode(buf.tobytes()).decode("ascii")
            try:
                _proc.stdin.write(f"DETECT {payload}\n")
                _proc.stdin.flush()
                deadline = time.time() + WORKER_DETECT_TIMEOUT_SECONDS
                while time.time() < deadline:
                    line = _proc.stdout.readline()
                    if not line:
                        if _proc.poll() is not None:
                            print("[proctor] phone service exited", flush=True)
                            return []
                        continue
                    line = line.strip()
                    if line.startswith("HITS "):
                        hits = json.loads(line[5:])
                        if hits:
                            print(f"[proctor] cell phone hit(s): {hits}", flush=True)
                        return hits
                    if line.startswith("ERROR "):
                        print(f"[proctor] phone service error: {line[6:]}", flush=True)
                        return []
                print("[proctor] phone service detect timeout", flush=True)
                return []
            except Exception as exc:
                print(f"[proctor] phone service failed: {exc}", flush=True)
                return []
