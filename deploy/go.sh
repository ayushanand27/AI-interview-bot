#!/usr/bin/env bash
# Full EC2 update in one command:
#   1) pull latest code
#   2) build frontend / migrate / restart
#   3) optionally patch SMTP + FRONTEND_URL if flags passed
#
# Everyday use (code only):
#   bash deploy/go.sh
#
# First-time email fix + redeploy:
#   bash deploy/go.sh \
#     --smtp-email you@gmail.com \
#     --smtp-password 'xxxx xxxx xxxx xxxx' \
#     --frontend-url https://ai-interview-bot.duckdns.org
#
# After domain HTTPS is configured:
#   bash deploy/go.sh --frontend-url https://yourdomain.com

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${APP_DIR}"

PATCH_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --smtp-email|--smtp-password|--frontend-url|--allowed-origins)
      PATCH_ARGS+=("$1" "$2")
      shift 2
      ;;
    *)
      echo "Unknown arg: $1"
      exit 1
      ;;
  esac
done

chmod +x deploy/deploy.sh deploy/patch_production_env.sh deploy/setup_https.sh 2>/dev/null || true

if [[ ${#PATCH_ARGS[@]} -gt 0 ]]; then
  echo "==> Patching production .env first..."
  bash deploy/patch_production_env.sh "${PATCH_ARGS[@]}"
fi

echo "==> Running full redeploy..."
bash deploy/deploy.sh

echo ""
echo "All done."
echo "Health: curl -s http://127.0.0.1/health"
echo "If you have a domain for webcam HTTPS: bash deploy/setup_https.sh yourdomain.com you@gmail.com"
