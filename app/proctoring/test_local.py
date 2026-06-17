import cv2
from eye_tracker import EyeTracker
from warning_manager import WarningManager

tracker = EyeTracker()
warning_mgr = WarningManager()

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Cannot open webcam!")
else:
    print("Webcam opened! Press Q to quit.")

while True:
    ret, frame = cap.read()
    frame = cv2.flip(frame, 1)  # 1 = horizontal flip (mirror)
    if not ret:
        break

    result = tracker.analyze_frame(frame)
    new_warning = warning_mgr.process_status(
    result["status"], result["message"], 
    result["gaze_direction"], result["confidence"]
    )

    # Status color
    if result["status"] == "ok":
        color = (0, 200, 0)       # Green
    elif result["status"] == "calibrating":
        color = (255, 165, 0)     # Orange
    else:
        color = (0, 0, 255)       # Red

    cv2.putText(frame, f"Status: {result['status']}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.putText(frame, f"Gaze: {result['gaze_direction']}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    penalty = warning_mgr.calculate_score_penalty()
    cv2.putText(frame, f"Penalty: -{penalty}%", (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    if new_warning:
        print(f"VIOLATION [{new_warning.severity}]: {new_warning.message}")

    cv2.imshow("Eye Tracker Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
tracker.release()
print("Integrity report:", warning_mgr.get_integrity_report())