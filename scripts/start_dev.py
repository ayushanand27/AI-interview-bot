#!/usr/bin/env python3
"""
Cross-network dev helper: start ngrok tunnels and update backend .env.

Usage (from project root):
    python scripts/start_dev.py

Requires ngrok on PATH (https://ngrok.com/download).

Starts:
  - Backend tunnel  -> localhost:8080 (ngrok API :4040)
  - Frontend tunnel -> localhost:5173 (ngrok API :4041) when possible

Updates .env:
  - FRONTEND_URL    -> public HTTPS URL for the frontend (email verification links)
  - ALLOWED_ORIGINS -> frontend + backend ngrok URLs and localhost dev origins

Prints VITE_API_URL for frontend/.env.local (set manually, then restart Vite).
Does NOT start uvicorn or npm — run those separately.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
BACKEND_PORT = 8080
FRONTEND_PORT = 5173
NGROK_BACKEND_API = "http://127.0.0.1:4040"
NGROK_FRONTEND_API = "http://127.0.0.1:4041"


def _read_env_lines() -> list[str]:
    if not ENV_PATH.exists():
        print(f"ERROR: {ENV_PATH} not found. Copy from .env.example first.")
        sys.exit(1)
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _set_env_value(lines: list[str], key: str, value: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(key)}=")
    out: list[str] = []
    replaced = False
    for line in lines:
        if pattern.match(line):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def _write_env(lines: list[str]) -> None:
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fetch_https_tunnel(api_base: str) -> str | None:
    try:
        with urllib.request.urlopen(f"{api_base}/api/tunnels", timeout=3) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None
    for tunnel in data.get("tunnels", []):
        public = tunnel.get("public_url") or ""
        if public.startswith("https://"):
            return public.rstrip("/")
    return None


def _wait_for_tunnel(api_base: str, label: str, timeout: float = 30.0) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = _fetch_https_tunnel(api_base)
        if url:
            return url
        time.sleep(0.5)
    print(f"WARNING: Timed out waiting for {label} ngrok tunnel at {api_base}")
    return None


def _start_ngrok(port: int, web_addr: str | None = None) -> subprocess.Popen:
    cmd = ["ngrok", "http", str(port), "--log=stdout"]
    if web_addr:
        cmd.extend(["--web-addr", web_addr])
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


def main() -> int:
    if not shutil.which("ngrok"):
        print("ERROR: ngrok not found on PATH. Install from https://ngrok.com/download")
        return 1

    print("Starting ngrok tunnels...")
    backend_proc = _start_ngrok(BACKEND_PORT)
    frontend_proc = _start_ngrok(FRONTEND_PORT, web_addr="127.0.0.1:4041")

    backend_url = _wait_for_tunnel(NGROK_BACKEND_API, "backend")
    frontend_url = _wait_for_tunnel(NGROK_FRONTEND_API, "frontend", timeout=15.0)

    if not backend_url:
        backend_proc.terminate()
        frontend_proc.terminate()
        print("ERROR: Could not obtain backend ngrok URL. Is port 8080/ngrok already in use?")
        return 1

    if not frontend_url:
        print(
            "NOTE: Frontend ngrok tunnel unavailable (second tunnel may need a paid plan). "
            "Email verification links require a public frontend URL — start manually:\n"
            f"  ngrok http {FRONTEND_PORT} --web-addr=127.0.0.1:4041\n"
        )
        frontend_url = backend_url  # fallback per single-tunnel setups

    origins = ",".join(
        dict.fromkeys(
            [
                frontend_url,
                backend_url,
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ]
        )
    )

    lines = _read_env_lines()
    lines = _set_env_value(lines, "FRONTEND_URL", frontend_url)
    lines = _set_env_value(lines, "ALLOWED_ORIGINS", origins)
    _write_env(lines)

    print()
    print("=" * 60)
    print("ngrok dev environment ready")
    print("=" * 60)
    print(f"Backend API (ngrok):   {backend_url}")
    print(f"Frontend (ngrok):      {frontend_url}")
    print()
    print("Updated .env:")
    print(f"  FRONTEND_URL={frontend_url}")
    print(f"  ALLOWED_ORIGINS={origins}")
    print()
    print("Next steps:")
    print("  1. Restart the backend (uvicorn) so it picks up .env changes")
    print("  2. Add to frontend/.env.local:")
    print(f"       VITE_API_URL={backend_url}")
    print("  3. Restart the frontend (npm run dev)")
    print("  4. Open the FRONTEND ngrok URL on any device/network")
    print()
    print("ngrok dashboards:")
    print(f"  Backend:  http://127.0.0.1:4040")
    print(f"  Frontend: http://127.0.0.1:4041")
    print()
    print("Press Ctrl+C to stop this script (ngrok processes keep running).")
    print("=" * 60)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nScript stopped. ngrok tunnels are still running in the background.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
