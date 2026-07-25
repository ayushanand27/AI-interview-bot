#!/usr/bin/env bash
# Enable HTTPS (Let's Encrypt) so webcam / getUserMedia works on EC2.
#
# Works with:
#   - Paid domains (example.com)
#   - Free DuckDNS (yourname.duckdns.org)  ← no www subdomain needed
#
# Prerequisites:
#   1. DNS A record / DuckDNS IP → your EC2 public IP
#   2. AWS Security Group: inbound TCP 80 and 443 open
#   3. DNS resolves: dig +short yourname.duckdns.org
#
# Usage on EC2:
#   bash deploy/setup_https.sh yourname.duckdns.org you@gmail.com
#   bash deploy/setup_https.sh example.com you@gmail.com --with-www

set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
WITH_WWW=0
if [[ "${3:-}" == "--with-www" ]]; then
  WITH_WWW=1
fi

if [[ -z "${DOMAIN}" || -z "${EMAIL}" ]]; then
  echo "Usage: bash deploy/setup_https.sh <domain> <email-for-letsencrypt> [--with-www]"
  echo "Example (DuckDNS): bash deploy/setup_https.sh mybot.duckdns.org you@gmail.com"
  exit 1
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_AVAILABLE="/etc/nginx/sites-available/ai-interview-bot"
SITE_ENABLED="/etc/nginx/sites-enabled/ai-interview-bot"

SERVER_NAMES="${DOMAIN}"
CERTBOT_DOMAINS=(-d "${DOMAIN}")
if [[ "${WITH_WWW}" -eq 1 ]]; then
  SERVER_NAMES="${DOMAIN} www.${DOMAIN}"
  CERTBOT_DOMAINS+=(-d "www.${DOMAIN}")
fi

echo "==> Installing certbot (if needed)..."
sudo apt-get update -y
sudo apt-get install -y certbot python3-certbot-nginx

echo "==> Writing nginx HTTP config with server_name ${SERVER_NAMES}..."
sudo tee "${SITE_AVAILABLE}" >/dev/null <<EOF
server {
    listen 80;
    server_name ${SERVER_NAMES};

    root ${APP_DIR}/frontend/dist;
    index index.html;
    client_max_body_size 12M;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }

    location = /health {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /proctor/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }
}
EOF

sudo ln -sf "${SITE_AVAILABLE}" "${SITE_ENABLED}"
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "==> Requesting Let's Encrypt certificate for ${DOMAIN}..."
sudo certbot --nginx "${CERTBOT_DOMAINS[@]}" \
  --non-interactive --agree-tos -m "${EMAIL}" --redirect

echo "==> Patching app FRONTEND_URL to HTTPS..."
bash "${APP_DIR}/deploy/patch_production_env.sh" --frontend-url "https://${DOMAIN}"

echo "==> Reloading nginx + restarting backend..."
sudo nginx -s reload
pm2 restart ai-interview-bot-backend

echo ""
echo "HTTPS ready. Open: https://${DOMAIN}"
echo "Webcam should work on that URL (secure context)."
echo "Certbot auto-renewal is installed via systemd timer."
