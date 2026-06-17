FROM python:3.11-slim

WORKDIR /app

# OpenCV / MediaPipe / ffmpeg for recording conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    APP_ENV=production

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# MediaPipe face landmarker + YOLO weights (lazy-loaded at runtime if missing)
WORKDIR /app/app/proctoring
RUN python download_model.py
WORKDIR /app
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

EXPOSE 8080

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
