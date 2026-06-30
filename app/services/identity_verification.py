"""OpenCV-based face detection for invite identity verification."""

from __future__ import annotations

import base64
from dataclasses import dataclass

import cv2
import numpy as np

# Histogram correlation below this flags low_identity_confidence for recruiter review.
IDENTITY_SIMILARITY_THRESHOLD = 0.35


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


def _normalize_image_size(image: np.ndarray) -> np.ndarray:
    """Upscale small images (ID thumbnails) and cap very large uploads."""
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest < 900:
        scale = 900 / longest
        return cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
    if longest > 1800:
        scale = 1800 / longest
        return cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )
    return image


def _gray_variants(gray: np.ndarray) -> list[np.ndarray]:
    variants = [cv2.equalizeHist(gray)]
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    variants.append(clahe.apply(gray))
    return variants


def _detect_faces(gray: np.ndarray, detector: cv2.CascadeClassifier) -> list[tuple[int, int, int, int]]:
    faces: list[tuple[int, int, int, int]] = []
    for enhanced in _gray_variants(gray):
        for min_neighbors in (5, 4, 3):
            for min_size in ((72, 72), (48, 48), (32, 32), (24, 24)):
                found = detector.detectMultiScale(
                    enhanced,
                    scaleFactor=1.08,
                    minNeighbors=min_neighbors,
                    minSize=min_size,
                )
                if len(found) > 0:
                    faces.extend([tuple(int(v) for v in rect) for rect in found])
                    break
            if faces:
                break
        if faces:
            break
    return faces


def _largest_face(image: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
    image = _normalize_image_size(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    if detector.empty():
        return None

    faces = _detect_faces(gray, detector)
    if not faces:
        return None

    x, y, w, h = max(faces, key=lambda rect: rect[2] * rect[3])
    pad = int(0.08 * max(w, h))
    y0 = max(0, y - pad)
    x0 = max(0, x - pad)
    y1 = min(image.shape[0], y + h + pad)
    x1 = min(image.shape[1], x + w + pad)
    face_roi = image[y0:y1, x0:x1]
    if face_roi.size == 0:
        return None
    return face_roi, (x0, y0, x1 - x0, y1 - y0)


def _face_histogram(face_bgr: np.ndarray) -> np.ndarray:
    resized = cv2.resize(face_bgr, (128, 128), interpolation=cv2.INTER_AREA)
    hist = cv2.calcHist(
        [resized], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256]
    )
    cv2.normalize(hist, hist)
    return hist


def _histogram_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(cv2.compareHist(a, b, cv2.HISTCMP_CORREL))


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
    if id_face is None:
        return FaceVerificationResult(
            verified=False,
            confidence=0.0,
            message=(
                "Could not detect a face on your ID photo. Upload a clear, well-lit image "
                "where your face is visible (not blurry or too small)."
            ),
        )

    selfie_face = _largest_face(selfie_image)
    if selfie_face is None:
        # Selfies are often mirrored — try a horizontal flip once.
        selfie_flipped = cv2.flip(selfie_image, 1)
        selfie_face = _largest_face(selfie_flipped)

    if selfie_face is None:
        return FaceVerificationResult(
            verified=False,
            confidence=0.0,
            message=(
                "Could not detect your face in the selfie. Face the camera directly, "
                "use good lighting, and capture again."
            ),
        )

    id_hist = _face_histogram(id_face[0])
    selfie_hist = _face_histogram(selfie_face[0])
    similarity = _histogram_similarity(id_hist, selfie_hist)

    # Try flipped selfie histogram if the first score is weak but faces were found.
    if similarity < IDENTITY_SIMILARITY_THRESHOLD:
        flipped_face = _largest_face(cv2.flip(selfie_image, 1))
        if flipped_face is not None:
            flipped_similarity = _histogram_similarity(
                id_hist, _face_histogram(flipped_face[0])
            )
            similarity = max(similarity, flipped_similarity)

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
