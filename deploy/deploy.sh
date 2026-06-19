#!/usr/bin/env bash
# Re-deploy / update SmartSkale InterviewBot on AWS EC2 after code changes.
# Run from the app root: chmod +x deploy/deploy.sh && ./deploy/deploy.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${APP_DIR}"

echo "==> Pulling latest code..."
git pull origin main

echo "==> Activating virtual environment..."
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Building frontend..."
cd frontend
npm ci
npm run build
cd "${APP_DIR}"

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Restarting backend..."
pm2 restart ai-interview-bot-backend

echo "==> Reloading nginx..."
sudo nginx -s reload

echo "Deploy complete."
