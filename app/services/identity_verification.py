"""OpenCV-based face detection for invite identity verification."""

from __future__ import annotations

import base64
from dataclasses import dataclass

import cv2
import numpy as np

# Histogram correlation below this flags low_identity_confidence for recruiter review.
IDENTITY_SIMILARITY_THRESHOLD = 0.4


@dataclass
class FaceVerificationResult:
    verified: bool
    confidence: float
    message: str
    low_identity_confidence: bool = False
    similarity_score: float = 0.0


def _decode_base64_image(data: str) -> np.ndarray | None:
    raw = data.strip()
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        binary = base64.b64decode(raw)
    except (ValueError, TypeError):
        return None
    arr = np.frombuffer(binary, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return image


def _largest_face(image: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda rect: rect[2] * rect[3])
    face_roi = image[y : y + h, x : x + w]
    return face_roi, (int(x), int(y), int(w), int(h))


def _face_histogram(face_bgr: np.ndarray) -> np.ndarray:
    hist = cv2.calcHist([face_bgr], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def verify_faces_from_base64(id_image_base64: str, selfie_base64: str) -> FaceVerificationResult:
    """Detect faces in ID and selfie; compare color histogram similarity."""
    id_image = _decode_base64_image(id_image_base64)
    selfie_image = _decode_base64_image(selfie_base64)

    if id_image is None or selfie_image is None:
        return FaceVerificationResult(
            verified=False,
            confidence=0.0,
            message="Could not read one or both images. Please upload valid JPG or PNG files.",
        )

    id_face = _largest_face(id_image)
    selfie_face = _largest_face(selfie_image)

    if id_face is None or selfie_face is None:
        return FaceVerificationResult(
            verified=False,
            confidence=0.0,
            message=(
                "Could not verify identity. Please ensure your face is clearly visible "
                "in both photos and try again."
            ),
        )

    id_hist = _face_histogram(id_face[0])
    selfie_hist = _face_histogram(selfie_face[0])
    similarity = float(cv2.compareHist(id_hist, selfie_hist, cv2.HISTCMP_CORREL))
    confidence = max(0.0, min(1.0, similarity))
    low_identity = similarity < IDENTITY_SIMILARITY_THRESHOLD

    message = "Identity verified successfully."
    if low_identity:
        message = (
            "Identity verified with low confidence — your session has been flagged "
            "for recruiter review."
        )

    return FaceVerificationResult(
        verified=True,
        confidence=confidence,
        message=message,
        low_identity_confidence=low_identity,
        similarity_score=similarity,
    )
