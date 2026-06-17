import urllib.request
urllib.request.urlretrieve(
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    "face_landmarker.task"
)
print("Downloaded!")