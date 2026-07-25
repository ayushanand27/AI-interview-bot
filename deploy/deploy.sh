#!/usr/bin/env bash
# Re-deploy / update AI Interview Bot on AWS EC2 after code changes.
# Run from the app root: bash deploy/deploy.sh  (or ./deploy/deploy.sh if executable)

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

echo "==> Pulling latest code (discard tracked local drift on server)..."
git fetch origin main
git reset --hard origin/main

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
if [[ -f /etc/nginx/sites-available/ai-interview-bot ]]; then
  # Keep existing site (may already have HTTPS from certbot). Only reload.
  sudo nginx -t
  sudo nginx -s reload
else
  echo "Installing baseline nginx site (HTTP)..."
  sudo cp "${APP_DIR}/deploy/nginx.conf" /etc/nginx/sites-available/ai-interview-bot
  sudo ln -sf /etc/nginx/sites-available/ai-interview-bot /etc/nginx/sites-enabled/ai-interview-bot
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo nginx -t
  sudo nginx -s reload
fi

echo "Deploy complete."
echo "Tip: one-command updates → bash deploy/go.sh"
echo "Webcam needs HTTPS → bash deploy/setup_https.sh yourdomain.com you@gmail.com"
