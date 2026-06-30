"""One-shot E2E API verification against local backend."""
from __future__ import annotations

import json
import sqlite3
import struct
import sys
import time
import uuid
import urllib.error
import urllib.request
import wave
from io import BytesIO
from pathlib import Path

BASE = "http://127.0.0.1:8080"
ROOT = Path(__file__).resolve().parents[1]
RESUME = ROOT / "test_resume.pdf"
DB_PATH = ROOT / "interview_bot.db"

results: list[dict] = []


def record(name: str, passed: bool, status: int | None, body, note: str = ""):
    results.append(
        {
            "name": name,
            "passed": passed,
            "status": status,
            "body": body,
            "note": note,
        }
    )


def http(
    method: str,
    path: str,
    *,
    data: dict | None = None,
    token: str | None = None,
    multipart: dict | None = None,
    timeout: int = 120,
):
    url = BASE + path
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if multipart is not None:
        boundary = uuid.uuid4().hex
        body = b""
        for name, value in multipart.get("fields", {}).items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            body += str(value).encode()
            body += b"\r\n"
        for name, spec in multipart.get("files", {}).items():
            filename, content, ctype = spec
            body += f"--{boundary}\r\n".encode()
            body += (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
            ).encode()
            body += f"Content-Type: {ctype}\r\n\r\n".encode()
            body += content
            body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "application/json" in ct:
                return resp.status, json.loads(raw.decode())
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode())
        except json.JSONDecodeError:
            return e.code, raw.decode(errors="replace")
    except urllib.error.URLError as e:
        return None, {"error": str(e.reason)}


def make_wav(seconds: float = 1.0) -> bytes:
    buf = BytesIO()
    rate = 16000
    nframes = int(rate * seconds)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<h", 0) * nframes)
    return buf.getvalue()


def make_blank_jpeg_b64() -> str:
    import base64

    try:
        import cv2
        import numpy as np

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", frame)
        if ok:
            return base64.b64encode(buf.tobytes()).decode()
    except ImportError:
        pass

    # Fallback: solid-color JPEG via minimal encoder
    from PIL import Image

    img = Image.new("RGB", (640, 480), color=(30, 30, 30))
    bio = BytesIO()
    img.save(bio, format="JPEG")
    return base64.b64encode(bio.getvalue()).decode()


def test_health():
    for path in ["/health", "/api/v1/status", "/proctor/health"]:
        code, body = http("GET", path)
        ok = code == 200
        record(f"TEST 1 GET {path}", ok, code, body)


def test_auth() -> tuple[str | None, str | None]:
    ts = int(time.time())
    candidate_email = f"e2e_candidate_{ts}@example.com"
    recruiter_email = f"e2e_recruiter_{ts}@example.com"
    password = "TestPass123!"

    code, body = http(
        "POST",
        "/api/v1/auth/register",
        data={
            "full_name": "E2E Candidate",
            "email": candidate_email,
            "password": password,
            "role": "candidate",
        },
    )
    record("TEST 2 POST /auth/register (candidate)", code == 201, code, body)

    candidate_token = None
    if code == 201 and isinstance(body, dict):
        candidate_token = body.get("data", {}).get("access_token")

    code, body = http(
        "POST",
        "/api/v1/auth/login",
        data={"email": candidate_email, "password": password},
    )
    record("TEST 2 POST /auth/login", code == 200, code, body)
    if candidate_token is None and code == 200 and isinstance(body, dict):
        candidate_token = body.get("data", {}).get("access_token")

    code, body = http("GET", "/api/v1/auth/me", token=candidate_token)
    record("TEST 2 GET /auth/me", code == 200, code, body)

    code, body = http(
        "POST",
        "/api/v1/auth/register",
        data={
            "full_name": "E2E Recruiter",
            "email": recruiter_email,
            "password": password,
            "role": "recruiter",
        },
    )
    record("TEST 2 POST /auth/register (recruiter)", code == 201, code, body)

    recruiter_token = None
    if code == 201 and isinstance(body, dict):
        recruiter_token = body.get("data", {}).get("access_token")

    return candidate_token, recruiter_token


def test_interview(token: str | None) -> str | None:
    if not token:
        record("TEST 3 interview flow", False, None, None, "No candidate token")
        return None
    if not RESUME.exists():
        record("TEST 3 interview flow", False, None, None, f"Missing {RESUME}")
        return None

    pdf = RESUME.read_bytes()
    code, body = http(
        "POST",
        "/api/v1/interviews/sessions",
        token=token,
        multipart={
            "fields": {
                "role_title": "Backend Engineer",
                "experience_level": "mid",
                "job_description": "Python FastAPI developer role.",
            },
            "files": {
                "resume_pdf": ("test_resume.pdf", pdf, "application/pdf"),
            },
        },
    )
    record("TEST 3 POST /sessions", code == 201, code, body)
    session_id = None
    if isinstance(body, dict):
        session_id = body.get("session_id")

    if not session_id:
        record("TEST 3 remaining steps", False, None, None, "No session_id")
        return None

    code, body = http(
        "POST",
        f"/api/v1/interviews/sessions/{session_id}/questions",
        token=token,
        data={"question_count": 2},
    )
    record("TEST 3 POST /questions", code == 200, code, body)

    code, body = http(
        "GET",
        f"/api/v1/interviews/sessions/{session_id}/current-question",
        token=token,
    )
    record("TEST 3 GET /current-question", code == 200, code, body)

    answer = (
        "I would design a REST API with FastAPI using async SQLAlchemy, "
        "JWT auth, and clear separation between routes and services."
    )
    code, body = http(
        "POST",
        f"/api/v1/interviews/sessions/{session_id}/answers",
        token=token,
        data={"answer": answer},
    )
    record("TEST 3 POST /answers (Q1)", code == 200, code, body)

    code, body = http(
        "GET",
        f"/api/v1/interviews/sessions/{session_id}/current-question",
        token=token,
    )
    record("TEST 3 GET /current-question (Q2)", code == 200, code, body)

    answer2 = (
        "For caching I would use Redis with TTL keys, cache-aside pattern, "
        "and invalidate on writes to keep data consistent."
    )
    code, body = http(
        "POST",
        f"/api/v1/interviews/sessions/{session_id}/answers",
        token=token,
        data={"answer": answer2},
    )
    record("TEST 3 POST /answers (Q2)", code == 200, code, body)

    code, body = http(
        "POST",
        f"/api/v1/interviews/sessions/{session_id}/end",
        token=token,
    )
    has_final = isinstance(body, dict) and body.get("final_score") is not None
    has_judgments = isinstance(body, dict) and body.get("answer_judgments")
    has_integrity = isinstance(body, dict) and (
        "integrity_penalty_percent" in body or body.get("integrity_report") is not None
    )
    record(
        "TEST 3 POST /end",
        code == 200 and has_final and bool(has_judgments) and has_integrity,
        code,
        body,
        note=f"final_score={has_final}, judgments={bool(has_judgments)}, integrity={has_integrity}",
    )
    return session_id


def test_proctoring():
    code, body = http("GET", "/proctor/health")
    record("TEST 4 GET /proctor/health", code == 200, code, body)

    code, body = http("POST", "/proctor/reset", data={"session_id": "e2e-test"})
    record("TEST 4 POST /proctor/reset", code == 200, code, body)

    frame = make_blank_jpeg_b64()
    code, body = http(
        "POST",
        "/proctor/analyze",
        data={"session_id": "e2e-test", "frame_base64": frame},
    )
    record("TEST 4 POST /proctor/analyze", code == 200, code, body)

    code, body = http("GET", "/proctor/warnings?session_id=e2e-test")
    record("TEST 4 GET /proctor/warnings", code == 200, code, body)

    code, body = http("GET", "/proctor/integrity-report?session_id=e2e-test")
    record("TEST 4 GET /proctor/integrity-report", code == 200, code, body)


def test_audio(token: str | None, session_id: str | None):
    if not token:
        record("TEST 5 audio-answer", False, None, None, "No token")
        return
    # Create a fresh session for audio-only test
    if not RESUME.exists():
        record("TEST 5 audio-answer", False, None, None, "Missing resume PDF")
        return
    pdf = RESUME.read_bytes()
    code, body = http(
        "POST",
        "/api/v1/interviews/sessions",
        token=token,
        multipart={
            "fields": {
                "role_title": "Audio Test",
                "experience_level": "mid",
                "job_description": "Audio transcription test.",
            },
            "files": {"resume_pdf": ("test_resume.pdf", pdf, "application/pdf")},
        },
    )
    if code != 201 or not isinstance(body, dict):
        record("TEST 5 create session for audio", False, code, body)
        return
    sid = body["session_id"]
    http(
        "POST",
        f"/api/v1/interviews/sessions/{sid}/questions",
        token=token,
        data={"question_count": 1},
    )
    wav = make_wav(1.5)
    code, body = http(
        "POST",
        f"/api/v1/interviews/sessions/{sid}/audio-answer",
        token=token,
        multipart={
            "fields": {"submit": "false"},
            "files": {"audio": ("test.wav", wav, "audio/wav")},
        },
    )
    has_text = isinstance(body, dict) and bool(body.get("transcribed_text"))
    record(
        "TEST 5 POST /audio-answer",
        code == 200 and has_text,
        code,
        body,
        note=f"transcribed_text present={has_text}",
    )


def test_recruiter(token: str | None, session_id: str | None):
    if not token:
        record("TEST 6 recruiter endpoints", False, None, None, "No recruiter token")
        return

    code, body = http("GET", "/api/v1/recruiter/sessions", token=token)
    record("TEST 6 GET /recruiter/sessions", code == 200, code, body)

    if not session_id:
        record("TEST 6 GET /recruiter/sessions/{id}", False, None, None, "No session_id")
        record("TEST 6 GET /recruiter/sessions/{id}/report", False, None, None, "No session_id")
        return

    code, body = http(
        "GET", f"/api/v1/recruiter/sessions/{session_id}", token=token
    )
    record("TEST 6 GET /recruiter/sessions/{id}", code == 200, code, body)

    code, body = http(
        "GET", f"/api/v1/recruiter/sessions/{session_id}/report", token=token
    )
    is_pdf = code == 200 and isinstance(body, (bytes, bytearray)) and len(body) > 100
    record(
        "TEST 6 GET /recruiter/sessions/{id}/report",
        is_pdf,
        code,
        f"<pdf {len(body) if isinstance(body, bytes) else 0} bytes>",
    )


def test_db():
    if not DB_PATH.exists():
        record("TEST 7 database query", False, None, None, f"Missing {DB_PATH}")
        return
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT session_id, status, role_title, final_score,
               proctoring_summary, answer_judgments
        FROM sessions ORDER BY updated_at DESC LIMIT 3
        """
    ).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    ok = len(data) > 0 and any(r.get("final_score") for r in data)
    record("TEST 7 DB sessions query", ok, None, data)


def main():
    test_health()
    candidate_token, recruiter_token = test_auth()
    session_id = test_interview(candidate_token)
    test_proctoring()
    test_audio(candidate_token, session_id)
    test_recruiter(recruiter_token, session_id)
    test_db()

    out = ROOT / "scripts" / "e2e_results.json"
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"E2E: {passed}/{total} passed")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"{status} | {r['name']} | HTTP {r['status']} | {r.get('note','')}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
