#!/usr/bin/env bash
# One-time (or rare) production .env patch on EC2.
# Does NOT commit secrets. Safe to re-run.
#
# Usage on EC2:
#   bash deploy/patch_production_env.sh \
#     --smtp-email you@gmail.com \
#     --smtp-password 'your16charapppassword' \
#     --frontend-url http://13.207.191.193
#
# After domain + HTTPS:
#   bash deploy/patch_production_env.sh --frontend-url https://yourdomain.com

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${APP_DIR}/.env"

SMTP_EMAIL=""
SMTP_PASSWORD=""
FRONTEND_URL=""
ALLOWED_ORIGINS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smtp-email) SMTP_EMAIL="$2"; shift 2 ;;
    --smtp-password) SMTP_PASSWORD="$2"; shift 2 ;;
    --frontend-url) FRONTEND_URL="$2"; shift 2 ;;
    --allowed-origins) ALLOWED_ORIGINS="$2"; shift 2 ;;
    *)
      echo "Unknown arg: $1"
      exit 1
      ;;
  esac
done

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Create it first (copy from .env.production.example)."
  exit 1
fi

upsert() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "${ENV_FILE}"; then
    # Escape & for sed replacement
    local escaped
    escaped="$(printf '%s' "${value}" | sed -e 's/[&|\\]/\\&/g')"
    sed -i "s|^${key}=.*|${key}=${escaped}|" "${ENV_FILE}"
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

if [[ -n "${SMTP_EMAIL}" ]]; then
  upsert "SMTP_EMAIL" "${SMTP_EMAIL}"
  echo "==> Updated SMTP_EMAIL"
fi

if [[ -n "${SMTP_PASSWORD}" ]]; then
  # Strip spaces (Gmail app passwords often copied with spaces)
  SMTP_PASSWORD="${SMTP_PASSWORD// /}"
  upsert "SMTP_PASSWORD" "${SMTP_PASSWORD}"
  echo "==> Updated SMTP_PASSWORD"
fi

if [[ -n "${FRONTEND_URL}" ]]; then
  upsert "FRONTEND_URL" "${FRONTEND_URL}"
  if [[ -z "${ALLOWED_ORIGINS}" ]]; then
    ALLOWED_ORIGINS="${FRONTEND_URL}"
  fi
  upsert "ALLOWED_ORIGINS" "${ALLOWED_ORIGINS}"
  echo "==> Updated FRONTEND_URL / ALLOWED_ORIGINS"
fi

upsert "SMTP_HOST" "smtp.gmail.com"
upsert "SMTP_PORT" "587"
upsert "APP_ENV" "production"

echo "==> Restarting backend to load .env..."
pm2 restart ai-interview-bot-backend

echo "Production env patched."
