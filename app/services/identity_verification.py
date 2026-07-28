"""OpenCV-based invite identity verification with liveness and OCR hints."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import re
from typing import Any

import cv2
import numpy as np

# Histogram correlation below this flags low_identity_confidence for recruiter review.
IDENTITY_SIMILARITY_THRESHOLD = 0.35
LIVENESS_STRONG_THRESHOLD = 0.75
LIVENESS_MIN_THRESHOLD = 0.5
ACTION_SHIFT_THRESHOLD = 0.06


@dataclass
class FaceVerificationResult:
    verified: bool
    confidence: float
    message: str
    low_identity_confidence: bool = False
    similarity_score: float = 0.0
    liveness_passed: bool = False
    liveness_confidence: float = 0.0
    warnings: list[str] | None = None
    ocr_name_match: bool | None = None
    ocr_name_detected: str | None = None
    ocr_document_number: str | None = None
    ocr_confidence: float | None = None
    best_selfie_index: int = 0
    evidence_metadata: dict[str, Any] | None = None


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


def _normalized_face_center(face_rect: tuple[int, int, int, int], image: np.ndarray) -> tuple[float, float]:
    x, y, w, h = face_rect
    img_h, img_w = image.shape[:2]
    return ((x + w / 2) / max(img_w, 1), (y + h / 2) / max(img_h, 1))


def _smile_detected(face_bgr: np.ndarray) -> bool:
    cascade_path = cv2.data.haarcascades + "haarcascade_smile.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    if detector.empty():
        return False
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    lower_face = gray[gray.shape[0] // 3 :, :]
    smiles = detector.detectMultiScale(
        lower_face,
        scaleFactor=1.7,
        minNeighbors=20,
        minSize=(24, 24),
    )
    return len(smiles) > 0


def _normalize_action(action: str) -> str:
    cleaned = str(action or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "center_face": "center",
        "look_center": "center",
        "move_head_left": "move_left",
        "look_left": "move_left",
        "turn_left": "move_left",
        "move_head_right": "move_right",
        "look_right": "move_right",
        "turn_right": "move_right",
        "smile_now": "smile",
    }
    return aliases.get(cleaned, cleaned)


def _evaluate_liveness(
    frame_images: list[np.ndarray], actions: list[str]
) -> tuple[bool, float, dict[str, Any], list[str]]:
    if not frame_images:
        return False, 0.0, {"mode": "multi_frame_sequence", "results": []}, [
            "No liveness frames were captured.",
        ]

    normalized_actions = [_normalize_action(a) for a in actions if str(a).strip()]
    if not normalized_actions:
        normalized_actions = ["center", "move_left", "move_right", "smile"]

    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    scored_checks = 0
    passed_checks = 0
    baseline_center_x: float | None = None

    for idx, action in enumerate(normalized_actions):
        if idx >= len(frame_images):
            results.append({"action": action, "passed": False, "reason": "frame_missing"})
            warnings.append(f"Missing selfie frame for liveness action: {action}.")
            scored_checks += 1
            continue

        image = frame_images[idx]
        detected = _largest_face(image)
        if detected is None:
            results.append({"action": action, "passed": False, "reason": "face_missing"})
            warnings.append(f"Could not detect your face for the '{action}' liveness step.")
            scored_checks += 1
            continue

        face_bgr, rect = detected
        center_x, center_y = _normalized_face_center(rect, image)
        if baseline_center_x is None:
            baseline_center_x = center_x

        passed = False
        detail: dict[str, Any] = {
            "action": action,
            "passed": False,
            "center_x": round(center_x, 4),
            "center_y": round(center_y, 4),
        }

        if action == "center":
            passed = True
        elif action == "move_left":
            passed = center_x <= (baseline_center_x - ACTION_SHIFT_THRESHOLD)
            detail["baseline_center_x"] = round(baseline_center_x, 4)
        elif action == "move_right":
            passed = center_x >= (baseline_center_x + ACTION_SHIFT_THRESHOLD)
            detail["baseline_center_x"] = round(baseline_center_x, 4)
        elif action == "smile":
            passed = _smile_detected(face_bgr)
        else:
            passed = True
            detail["reason"] = "unsupported_action_treated_as_present"

        detail["passed"] = passed
        results.append(detail)
        scored_checks += 1
        if passed:
            passed_checks += 1
        else:
            warnings.append(f"Liveness check '{action}' did not pass clearly.")

    confidence = passed_checks / max(scored_checks, 1)
    passed = confidence >= LIVENESS_MIN_THRESHOLD
    return passed, confidence, {"mode": "multi_frame_sequence", "results": results}, warnings


def _extract_id_text(image: np.ndarray) -> tuple[str | None, float | None]:
    try:
        import pytesseract  # type: ignore
    except Exception:
        return None, None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    text = pytesseract.image_to_string(gray, config="--psm 6")
    cleaned = " ".join(text.split())
    if not cleaned:
        return None, None
    # Best-effort confidence proxy since pytesseract text output does not include scores here.
    alpha_num = len(re.findall(r"[A-Z0-9]", cleaned.upper()))
    confidence = min(alpha_num / 80.0, 1.0)
    return cleaned, confidence


def _extract_document_number(ocr_text: str | None) -> str | None:
    if not ocr_text:
        return None
    patterns = [
        r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",  # PAN
        r"\b[0-9]{4}\s?[0-9]{4}\s?[0-9]{4}\b",  # Aadhaar-like
        r"\b[A-Z][0-9]{7}\b",  # Passport-like
        r"\b[A-Z0-9]{8,18}\b",
    ]
    uppercase = ocr_text.upper()
    for pattern in patterns:
        match = re.search(pattern, uppercase)
        if match:
            return match.group(0).replace(" ", "")
    return None


def _extract_candidate_name(ocr_text: str | None, expected_name: str | None) -> tuple[bool | None, str | None]:
    if not ocr_text:
        return None, None
    text = re.sub(r"[^A-Z ]", " ", ocr_text.upper())
    text = re.sub(r"\s+", " ", text).strip()
    detected = " ".join(text.split()[:6]) or None
    if not expected_name:
        return None, detected

    expected_tokens = [
        token
        for token in re.sub(r"[^A-Z ]", " ", expected_name.upper()).split()
        if len(token) >= 3
    ]
    if not expected_tokens:
        return None, detected
    matched = sum(1 for token in expected_tokens if token in text)
    return (matched / len(expected_tokens)) >= 0.6, detected


def verify_faces_from_base64(
    id_image_base64: str,
    selfie_base64: str,
    *,
    selfie_frames_base64: list[str] | None = None,
    liveness_actions: list[str] | None = None,
    expected_candidate_name: str | None = None,
) -> FaceVerificationResult:
    """Detect faces in ID and selfies; compare similarity plus liveness/OCR hints."""
    id_image = _decode_base64_image(id_image_base64)
    primary_selfie = _decode_base64_image(selfie_base64)

    if id_image is None or primary_selfie is None:
        return FaceVerificationResult(
            verified=False,
            confidence=0.0,
            message="Could not read one or both images. Please upload valid JPG or PNG files.",
            warnings=[],
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
            warnings=[],
        )

    warnings: list[str] = []
    frame_images: list[np.ndarray] = []
    raw_frames = [primary_selfie, *[_decode_base64_image(item) for item in (selfie_frames_base64 or [])]]
    for frame in raw_frames:
        if frame is not None:
            frame_images.append(frame)

    if not frame_images:
        return FaceVerificationResult(
            verified=False,
            confidence=0.0,
            message=(
                "Could not detect your face in the selfie. Face the camera directly, "
                "use good lighting, and capture again."
            ),
            warnings=[],
        )

    id_hist = _face_histogram(id_face[0])
    similarity = -1.0
    best_selfie_index = 0
    valid_selfie_count = 0

    for idx, selfie_image in enumerate(frame_images):
        selfie_face = _largest_face(selfie_image)
        if selfie_face is None:
            flipped_face = _largest_face(cv2.flip(selfie_image, 1))
            selfie_face = flipped_face
        if selfie_face is None:
            continue
        valid_selfie_count += 1
        current_similarity = _histogram_similarity(id_hist, _face_histogram(selfie_face[0]))
        if current_similarity > similarity:
            similarity = current_similarity
            best_selfie_index = idx

    if valid_selfie_count == 0:
        return FaceVerificationResult(
            verified=False,
            confidence=0.0,
            message=(
                "Could not detect your face in the selfie sequence. Face the camera directly, "
                "use good lighting, and capture again."
            ),
            warnings=[],
        )

    confidence = max(0.0, min(1.0, similarity))
    low_identity = similarity < IDENTITY_SIMILARITY_THRESHOLD
    if valid_selfie_count < 2:
        warnings.append("Only one clear selfie frame was detected; recruiter review may be required.")
        low_identity = True

    liveness_passed, liveness_confidence, liveness_metadata, liveness_warnings = _evaluate_liveness(
        frame_images,
        liveness_actions or [],
    )
    warnings.extend(liveness_warnings)

    ocr_text, ocr_confidence = _extract_id_text(id_image)
    ocr_name_match, ocr_name_detected = _extract_candidate_name(
        ocr_text,
        expected_candidate_name,
    )
    ocr_document_number = _extract_document_number(ocr_text)

    if ocr_name_match is False:
        warnings.append("The name detected on the ID did not clearly match the candidate details.")
        low_identity = True
    elif ocr_text is None:
        warnings.append("OCR support is unavailable in this environment, so ID text could not be checked.")

    verified = True
    if liveness_confidence < LIVENESS_MIN_THRESHOLD:
        verified = False
    elif liveness_confidence < LIVENESS_STRONG_THRESHOLD:
        low_identity = True

    message = "Identity verified successfully."
    if not verified:
        message = (
            "Liveness verification was not strong enough. Re-capture the guided selfie sequence "
            "with clearer movement and lighting."
        )
    elif low_identity:
        message = (
            "Identity verified with additional review signals — your session has been flagged "
            "for recruiter review."
        )

    return FaceVerificationResult(
        verified=verified,
        confidence=confidence,
        message=message,
        low_identity_confidence=low_identity,
        similarity_score=similarity,
        liveness_passed=liveness_passed,
        liveness_confidence=liveness_confidence,
        warnings=warnings,
        ocr_name_match=ocr_name_match,
        ocr_name_detected=ocr_name_detected,
        ocr_document_number=ocr_document_number,
        ocr_confidence=ocr_confidence,
        best_selfie_index=best_selfie_index,
        evidence_metadata={
            "valid_selfie_frames": valid_selfie_count,
            "best_selfie_index": best_selfie_index,
            "liveness": liveness_metadata,
        },
    )
