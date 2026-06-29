#!/usr/bin/env bash
# Re-deploy / update SmartSkale InterviewBot on AWS EC2 after code changes.
# Run from the app root: chmod +x deploy/deploy.sh && ./deploy/deploy.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${APP_DIR}"

DEPLOY_USER="${SUDO_USER:-$(whoami)}"

echo "==> Ensuring app directory is owned by ${DEPLOY_USER}..."
if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_DIR}"
else
  if [[ ! -w "${APP_DIR}/.git" ]]; then
    echo "Fixing git permissions (one-time)..."
    sudo chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_DIR}"
  fi
fi

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
python scripts/bootstrap_db.py

echo "==> Restarting backend..."
pm2 restart ai-interview-bot-backend

echo "==> Reloading nginx..."
sudo nginx -s reload

echo "Deploy complete."
