"""Quick SMTP connectivity check — run on EC2 or local.

  python scripts/test_smtp.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.core.config import get_settings
from app.services.email_service import _send_email


def main() -> int:
    get_settings.cache_clear()
    from app.core.config import settings

    print(f"APP_ENV={settings.APP_ENV}")
    print(f"FRONTEND_URL={settings.FRONTEND_URL}")
    print(f"effective_frontend_url={settings.effective_frontend_url}")
    print(f"SMTP_HOST={settings.SMTP_HOST}:{settings.SMTP_PORT}")
    print(f"SMTP_EMAIL={settings.SMTP_EMAIL!r}")
    print(f"SMTP_PASSWORD length={len(settings.SMTP_PASSWORD or '')}")

    if not settings.SMTP_EMAIL or not settings.SMTP_PASSWORD:
        print("FAIL: SMTP_EMAIL or SMTP_PASSWORD missing in .env")
        return 1

    to = settings.SMTP_EMAIL
    ok = _send_email(
        to,
        "AI Interview Bot SMTP test",
        "<p>If you received this, SMTP works on this server.</p>",
    )
    print(f"send_ok={ok}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
