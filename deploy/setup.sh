#!/usr/bin/env bash
# One-time AWS EC2 (Ubuntu) setup for AI Interview Bot.
# Run on a fresh instance: chmod +x deploy/setup.sh && sudo ./deploy/setup.sh
#
# Before running:
#   1. Set REPO_URL below to your GitHub repo
#   2. Open EC2 security group ports 22, 80 (and 8080 only if debugging backend directly)
#   3. Create /var/www/ai-interview-bot/.env with production secrets after this script finishes

set -euo pipefail

# ── Configuration (edit before first run) ─────────────────────────────────────
REPO_URL="https://github.com/ayushanand27/AI-interview-bot.git"
BRANCH="main"
APP_DIR="/var/www/ai-interview-bot"
# ─────────────────────────────────────────────────────────────────────────────

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root: sudo ./deploy/setup.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> Updating apt packages..."
apt-get update -y
apt-get upgrade -y

echo "==> Installing system dependencies..."
apt-get install -y \
  python3 \
  python3-pip \
  python3-venv \
  nginx \
  git \
  curl \
  ffmpeg \
  libgl1 \
  libglib2.0-0 \
  libsm6 \
  libxext6 \
  libxrender1

echo "==> Installing Node.js 20.x..."
if ! command -v node >/dev/null 2>&1 || [[ "$(node -v | cut -d. -f1 | tr -d v)" -lt 18 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

echo "==> Installing PM2 globally..."
npm install -g pm2

echo "==> Cloning application to ${APP_DIR}..."
mkdir -p "$(dirname "${APP_DIR}")"
if [[ -d "${APP_DIR}/.git" ]]; then
  echo "    Repo already exists — pulling latest ${BRANCH}..."
  git -C "${APP_DIR}" fetch origin
  git -C "${APP_DIR}" checkout "${BRANCH}"
  git -C "${APP_DIR}" pull origin "${BRANCH}"
else
  git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

cd "${APP_DIR}"

echo "==> Creating Python virtual environment..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Downloading proctoring models..."
python app/proctoring/download_model.py
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

echo "==> Building frontend (same-origin — leave VITE_API_URL unset)..."
cd frontend
npm ci
npm run build
cd "${APP_DIR}"

echo "==> Creating upload directory..."
mkdir -p uploads data
DEPLOY_USER="${SUDO_USER:-ubuntu}"
if id "${DEPLOY_USER}" >/dev/null 2>&1; then
  chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_DIR}"
  chown -R www-data:www-data uploads data frontend/dist 2>/dev/null || true
else
  chown -R www-data:www-data uploads data frontend/dist 2>/dev/null || true
fi

if [[ ! -f .env ]]; then
  echo "==> WARNING: ${APP_DIR}/.env not found."
  echo "    Copy .env.example → .env and fill in production values before starting."
  cp .env.example .env
fi

echo "==> Running database migrations..."
python scripts/bootstrap_db.py

echo "==> Configuring nginx..."
cp deploy/nginx.conf /etc/nginx/sites-available/ai-interview-bot
ln -sf /etc/nginx/sites-available/ai-interview-bot /etc/nginx/sites-enabled/ai-interview-bot
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl reload nginx

echo "==> Starting backend with PM2..."
pm2 delete ai-interview-bot-backend 2>/dev/null || true
pm2 start deploy/ecosystem.config.js
pm2 save
pm2 startup systemd -u "${SUDO_USER:-root}" --hp "/home/${SUDO_USER:-root}" || true

echo ""
echo "Setup complete."
echo "  App directory: ${APP_DIR}"
echo "  Frontend:      http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'YOUR_EC2_IP')/"
echo "  API health:    http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'YOUR_EC2_IP')/health"
echo ""
echo "Next steps:"
echo "  1. Edit ${APP_DIR}/.env with production secrets (see README AWS Deployment checklist)"
echo "  2. pm2 restart ai-interview-bot-backend"
echo "  3. sudo nginx -s reload"
