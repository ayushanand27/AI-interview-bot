import cv2
import numpy as np
from typing import Tuple
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import os

LEFT_EYE_OUTER = 33
LEFT_EYE_INNER = 133
LEFT_EYE_TOP = 159
LEFT_EYE_BOTTOM = 145
RIGHT_EYE_OUTER = 263
RIGHT_EYE_INNER = 362
RIGHT_EYE_TOP = 386
RIGHT_EYE_BOTTOM = 374
NOSE_TIP = 1
CHIN = 152
LEFT_CHEEK = 234
RIGHT_CHEEK = 454

MSG_NO_FACE = "No face detected - candidate may have left"
MSG_MULTIPLE_FACES = "Multiple people detected - possible assistance"
MSG_LOOKING_SIDEWAYS = "Candidate looking away - head turned sideways"
MSG_LOOKING_DOWN = "Candidate looking down - possible notes or phone"
MSG_LOOKING_UP = "Candidate looking up - possible external display"
MSG_ATTENTIVE = "Candidate is attentive"

# ── Thresholds (loosened to reduce false positives) ───────────────────────
# Previous: MIN_FACE_COVERAGE=0.04, symmetry>0.45, down ratio>3.5, up ratio<0.3
MIN_FACE_COVERAGE = 0.03
FACE_SYMMETRY_THRESHOLD = 0.55  # was 0.45
HEAD_DOWN_RATIO_THRESHOLD = 4.5  # was 3.5
HEAD_UP_RATIO_THRESHOLD = 0.22  # was 0.3
# Run head-pose / partial-face checks every Nth analyze call (client ~3s interval)
HEAD_POSE_CHECK_INTERVAL = 3


class EyeTracker:
    def __init__(self):
        model_path = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=2,
            min_face_detection_confidence=0.3,
            min_face_presence_confidence=0.3,
            min_tracking_confidence=0.3
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)
        self._analyze_frame_count = 0

        print("EyeTracker initialized.")

    def analyze_frame(self, frame: np.ndarray) -> dict:
        self._analyze_frame_count += 1
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = self.landmarker.detect(mp_image)

        if not results.face_landmarks:
            return {"status": "no_face", "num_faces": 0,
                    "gaze_direction": "unknown", "confidence": 1.0,
                    "message": MSG_NO_FACE}

        num_faces = len(results.face_landmarks)
        if num_faces > 1:
            return {"status": "multiple_faces", "num_faces": num_faces,
                    "gaze_direction": "unknown", "confidence": 1.0,
                    "message": MSG_MULTIPLE_FACES}

        landmarks = results.face_landmarks[0]
        h, w = frame.shape[:2]

        # Skip strict head-pose checks on most frames to ignore brief natural movement.
        if self._analyze_frame_count % HEAD_POSE_CHECK_INTERVAL != 0:
            return {"status": "ok", "num_faces": 1,
                    "gaze_direction": "center", "confidence": 0.95,
                    "message": MSG_ATTENTIVE}

        if not self._check_face_complete(landmarks, w, h):
            print(
                "[proctor] looking_away: reason=face_not_complete "
                "(bounds/coverage/symmetry — no head-pose ratio)"
            )
            return {"status": "looking_away", "num_faces": 1,
                    "gaze_direction": "away", "confidence": 0.95,
                    "message": MSG_LOOKING_SIDEWAYS}

        head_status, head_ratio, nose_chin_dist, eye_nose_dist = self._check_head_pose(
            landmarks, w, h
        )
        if head_status == "down":
            print(
                "[proctor] looking_away: reason=head_pose "
                f"head_status={head_status!r} "
                f"ratio={head_ratio} "
                f"(nose_chin_dist={nose_chin_dist}, eye_nose_dist={eye_nose_dist}; "
                f"down if ratio>{HEAD_DOWN_RATIO_THRESHOLD}, "
                f"up if ratio<{HEAD_UP_RATIO_THRESHOLD})"
            )
            return {"status": "looking_away", "num_faces": 1,
                    "gaze_direction": "down", "confidence": 0.75,
                    "message": MSG_LOOKING_DOWN}
        if head_status == "up":
            print(
                "[proctor] looking_away: reason=head_pose "
                f"head_status={head_status!r} "
                f"ratio={head_ratio} "
                f"(nose_chin_dist={nose_chin_dist}, eye_nose_dist={eye_nose_dist}; "
                f"down if ratio>{HEAD_DOWN_RATIO_THRESHOLD}, "
                f"up if ratio<{HEAD_UP_RATIO_THRESHOLD})"
            )
            return {"status": "looking_away", "num_faces": 1,
                    "gaze_direction": "up", "confidence": 0.75,
                    "message": MSG_LOOKING_UP}

        return {"status": "ok", "num_faces": 1,
                "gaze_direction": "center", "confidence": 0.95,
                "message": MSG_ATTENTIVE}

    def _check_face_complete(self, landmarks, w, h) -> bool:
        """Check face is fully in frame and not turned away"""
        def lm(idx):
            pt = landmarks[idx]
            return np.array([pt.x * w, pt.y * h])

        try:
            nose = lm(NOSE_TIP)
            chin = lm(CHIN)
            left_cheek = lm(LEFT_CHEEK)
            right_cheek = lm(RIGHT_CHEEK)

            points = [nose, chin, left_cheek, right_cheek]
            for pt in points:
                if pt[0] < 0 or pt[0] > w or pt[1] < 0 or pt[1] > h:
                    return False

            face_width = abs(right_cheek[0] - left_cheek[0])
            face_height = abs(chin[1] - landmarks[10].y * h)
            frame_area = w * h
            face_area = face_width * face_height

            if face_area / frame_area < MIN_FACE_COVERAGE:
                return False

            nose_x = nose[0]
            face_center_x = (left_cheek[0] + right_cheek[0]) / 2
            symmetry = abs(nose_x - face_center_x) / (face_width + 1e-6)
            if symmetry > FACE_SYMMETRY_THRESHOLD:
                return False

            return True
        except Exception:
            return True

    def _check_head_pose(self, landmarks, w, h) -> tuple[str, float | None, float | None, float | None]:
        """
        Detect if head is tilted down (looking at phone) or up.

        Returns (status, ratio, nose_chin_dist, eye_nose_dist).
        ratio = nose_chin_dist / eye_nose_dist when both distances are positive.
        """
        def lm(idx):
            pt = landmarks[idx]
            return np.array([pt.x * w, pt.y * h])

        try:
            nose = lm(NOSE_TIP)
            chin = lm(CHIN)
            left_eye_top = lm(LEFT_EYE_TOP)
            right_eye_top = lm(RIGHT_EYE_TOP)

            eye_mid_y = (left_eye_top[1] + right_eye_top[1]) / 2

            nose_chin_dist = float(chin[1] - nose[1])
            eye_nose_dist = float(nose[1] - eye_mid_y)

            if nose_chin_dist > 0 and eye_nose_dist > 0:
                ratio = nose_chin_dist / (eye_nose_dist + 1e-6)
                if ratio > HEAD_DOWN_RATIO_THRESHOLD:
                    return "down", ratio, nose_chin_dist, eye_nose_dist
                if ratio < HEAD_UP_RATIO_THRESHOLD:
                    return "up", ratio, nose_chin_dist, eye_nose_dist
                return "forward", ratio, nose_chin_dist, eye_nose_dist

            return "forward", None, nose_chin_dist, eye_nose_dist
        except Exception:
            return "forward", None, None, None

    def release(self):
        self.landmarker.close()
