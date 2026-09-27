#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p uploads data

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing — run install first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python scripts/bootstrap_db.py
