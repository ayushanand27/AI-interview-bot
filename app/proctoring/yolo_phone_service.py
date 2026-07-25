"""Standalone YOLO cell-phone detector process.

Run as: python -m app.proctoring.yolo_phone_service

Protocol (stdin/stdout, one job per line after ready):
  Parent -> child:  DETECT <base64-jpeg>
  Child  -> parent: READY
  Child  -> parent: HITS <json-list>
  Child  -> parent: ERROR <message>
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

CELL_PHONE_CONFIDENCE = 0.25
YOLO_IMGSZ = 640
MSG = "Cell phone detected near candidate — possible cheating aid"


def _model_path() -> str:
    root = Path(__file__).resolve().parents[2]
    candidate = root / "yolov8n.pt"
    return str(candidate) if candidate.is_file() else "yolov8n.pt"


def main() -> None:
    import cv2
    import numpy as np
    from ultralytics import YOLO

    model = YOLO(_model_path())
    phone_ids = {
        idx
        for idx, name in model.names.items()
        if str(name).lower() in {"cell phone", "cell_phone"}
    } or {67}

    print("READY", flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line == "STOP":
            break
        if not line.startswith("DETECT "):
            print("ERROR bad_command", flush=True)
            continue
        try:
            raw = base64.b64decode(line[7:])
            frame = cv2.imdecode(
                np.frombuffer(raw, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            if frame is None or frame.size == 0:
                print("HITS []", flush=True)
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
            hits = []
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
                            "message": MSG,
                        }
                    )
            print("HITS " + json.dumps(hits), flush=True)
        except Exception as exc:
            print(f"ERROR {exc}", flush=True)


if __name__ == "__main__":
    main()
