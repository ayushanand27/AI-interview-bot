#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  # SQLite avoids Docker Postgres in Cloud Agent VMs (Postgres: docker compose up -d).
  sed -i 's|^DATABASE_URL=.*|DATABASE_URL=sqlite+aiosqlite:///./interview_bot.db|' .env
  if [[ -n "${SECRET_KEY:-}" ]]; then
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" .env
  else
    sed -i 's|^SECRET_KEY=.*|SECRET_KEY=cloud-agent-dev-secret-change-in-production|' .env
  fi
  if [[ -n "${GROQ_API_KEY:-}" ]]; then
    sed -i "s|^GROQ_API_KEY=.*|GROQ_API_KEY=${GROQ_API_KEY}|" .env
  else
    sed -i 's|^GROQ_API_KEY=.*|GROQ_API_KEY=gsk-placeholder-for-local-dev|' .env
  fi
fi

python app/proctoring/download_model.py
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

cd frontend
npm ci
cd "$ROOT"

mkdir -p uploads data
python scripts/bootstrap_db.py
