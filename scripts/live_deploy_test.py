#!/usr/bin/env python3
"""End-to-end API tests against the deployed production instance (no local DB required)."""

from __future__ import annotations

import io
import sys
import uuid
from pathlib import Path

import requests

BASE = "http://13.207.191.193"
ROOT = Path(__file__).resolve().parents[1]
RESUME_PDF = ROOT / "test_resume.pdf"
TIMEOUT = 120

results: list[str] = []


def test(name: str, passed: bool, details: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    line = f"{status} | {name} | {details}"
    results.append(line)
    print(line)


def unwrap(body: dict, key: str, default=None):
    if key in body:
        return body[key]
    data = body.get("data")
    if isinstance(data, dict) and key in data:
        return data[key]
    return default


def token_from_login(resp: requests.Response) -> str:
    try:
        return unwrap(resp.json(), "access_token", "") or ""
    except Exception:
        return ""


def main() -> int:
    if not RESUME_PDF.exists():
        print(f"Missing {RESUME_PDF}")
        return 1

    uid = uuid.uuid4().hex[:8]
    candidate_email = f"live_cand_{uid}@example.com"
    recruiter_email = f"live_rec_{uid}@example.com"
    invite_email = f"live_inv_{uid}@example.com"
    jd_text = (
        "Python Developer with FastAPI, REST APIs, SQLAlchemy, async programming, "
        "and PostgreSQL. Build scalable backend services."
    )

    # ── Infrastructure ─────────────────────────────────────────────
    r = requests.get(f"{BASE}/", timeout=30)
    test("Frontend HTML loads", r.status_code == 200 and "AI Interview Engine" in r.text)

    r = requests.get(f"{BASE}/health", timeout=15)
    test("Backend /health", r.status_code == 200 and r.json().get("status") == "ok")

    r = requests.get(f"{BASE}/proctor/health", timeout=15)
    test("Proctor /health", r.status_code == 200)

    r = requests.get(f"{BASE}/api/v1/status", timeout=15)
    status = r.json() if r.status_code == 200 else {}
    test("API /status", r.status_code == 200)
    test("DB connected (status)", status.get("database_connected") is True)
    test("Proctoring loaded (status)", status.get("proctoring_loaded") is True)

    r = requests.get(f"{BASE}/api/v1/auth/me", timeout=15)
    test("Auth enforced /me", r.status_code == 401)

    # ── Candidate auth ───────────────────────────────────────────
    r = requests.post(
        f"{BASE}/api/v1/auth/register",
        json={
            "full_name": "Live Test Candidate",
            "email": candidate_email,
            "password": "password123",
            "role": "candidate",
        },
        timeout=30,
    )
    test("Register candidate", r.status_code == 201, f"status={r.status_code}")

    r = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": candidate_email, "password": "password123"},
        timeout=15,
    )
    cand_token = token_from_login(r)
    test("Login candidate", r.status_code == 200 and bool(cand_token))
    cand_headers = {"Authorization": f"Bearer {cand_token}"}

    r = requests.post(
        f"{BASE}/api/v1/auth/forgot-password",
        json={"email": candidate_email},
        timeout=30,
    )
    test("Forgot password", r.status_code == 200)

    r = requests.post(
        f"{BASE}/api/v1/auth/reset-password",
        json={"token": "invalid-token-00000000", "new_password": "newpass12345"},
        timeout=15,
    )
    test("Reset password rejects bad token", r.status_code == 400)

    r = requests.post(
        f"{BASE}/api/v1/auth/resend-verification",
        json={"email": candidate_email},
        timeout=30,
    )
    test("Resend verification", r.status_code == 200)

    with RESUME_PDF.open("rb") as resume_file:
        r = requests.post(
            f"{BASE}/api/v1/interviews/sessions",
            headers=cand_headers,
            files={"resume_pdf": ("resume.pdf", resume_file, "application/pdf")},
            data={
                "job_description": jd_text,
                "role_title": "Python Developer",
                "experience_level": "mid",
            },
            timeout=60,
        )
    test(
        "Unverified candidate blocked from session",
        r.status_code == 403,
        str(r.json())[:80],
    )

    # ── Recruiter + Groq assessment (JD questions) ─────────────────
    r = requests.post(
        f"{BASE}/api/v1/auth/register",
        json={
            "full_name": "Live Test Recruiter",
            "email": recruiter_email,
            "password": "password123",
            "role": "recruiter",
        },
        timeout=30,
    )
    test("Register recruiter", r.status_code == 201)

    r = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": recruiter_email, "password": "password123"},
        timeout=15,
    )
    rec_token = token_from_login(r)
    test("Login recruiter", r.status_code == 200 and bool(rec_token))
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    r = requests.post(
        f"{BASE}/api/v1/recruiter/create-assessment",
        headers=rec_headers,
        data={
            "jd_text": jd_text,
            "question_count": "2",
            "difficulty": "medium",
            "expiry_hours": "48",
        },
        timeout=TIMEOUT,
    )
    invite_token = ""
    questions_preview = []
    if r.status_code == 200:
        body = r.json()
        data = body.get("data", body)
        invite_token = data.get("token", "") if isinstance(data, dict) else ""
        questions_preview = data.get("questions_preview", []) if isinstance(data, dict) else []
    test(
        "Recruiter create assessment (Groq JD questions)",
        r.status_code == 200 and bool(invite_token),
        f"status={r.status_code} preview={len(questions_preview)} q",
    )
    test(
        "Assessment has question preview",
        len(questions_preview) >= 1,
        str(questions_preview[0])[:60] if questions_preview else "none",
    )

    # ── Invite flow (auto-verified candidate) ────────────────────
    inv_token = ""
    inv_headers = {}
    inv_session_id = ""

    if invite_token:
        r = requests.get(f"{BASE}/api/v1/invite/{invite_token}", timeout=30)
        test("Validate invite link", r.status_code == 200 and r.json().get("valid") is True)

        r = requests.post(
            f"{BASE}/api/v1/invite/{invite_token}/register",
            json={"name": "Live Invite Candidate", "email": invite_email, "phone": "9999999999"},
            timeout=60,
        )
        inv_body = r.json().get("data", r.json()) if r.status_code in (200, 201) else {}
        inv_session_id = inv_body.get("session_id", "") if isinstance(inv_body, dict) else ""
        inv_access = inv_body.get("access_token", "") if isinstance(inv_body, dict) else ""
        inv_headers = {"Authorization": f"Bearer {inv_access}"} if inv_access else {}
        test(
            "Invite candidate register",
            r.status_code in (200, 201) and bool(inv_session_id),
            f"session={inv_session_id[:12] if inv_session_id else 'none'}",
        )

    # Invite interview uses pre-set questions — answer + judge via Groq
    if inv_session_id and inv_headers:
        r = requests.get(
            f"{BASE}/api/v1/interviews/sessions/{inv_session_id}/current-question",
            headers=inv_headers,
            timeout=30,
        )
        q1 = r.json().get("question", "") if r.status_code == 200 else ""
        test("Invite get question 1", r.status_code == 200 and bool(q1), q1[:50])

        r = requests.post(
            f"{BASE}/api/v1/interviews/sessions/{inv_session_id}/answers",
            headers=inv_headers,
            json={
                "answer": (
                    "I have built REST APIs with FastAPI and SQLAlchemy, using async endpoints "
                    "and proper validation for production backends."
                )
            },
            timeout=TIMEOUT,
        )
        test("Invite submit answer 1 (Groq judge)", r.status_code == 200, f"status={r.status_code}")

        r = requests.get(
            f"{BASE}/api/v1/interviews/sessions/{inv_session_id}/current-question",
            headers=inv_headers,
            timeout=30,
        )
        test("Invite get question 2", r.status_code == 200)

        r = requests.post(
            f"{BASE}/api/v1/interviews/sessions/{inv_session_id}/answers",
            headers=inv_headers,
            json={
                "answer": (
                    "For debugging production issues I check logs, reproduce locally, "
                    "add tests, and roll out fixes with monitoring."
                )
            },
            timeout=TIMEOUT,
        )
        test("Invite submit answer 2 (Groq judge)", r.status_code == 200)

        r = requests.post(
            f"{BASE}/api/v1/interviews/sessions/{inv_session_id}/end",
            headers=inv_headers,
            timeout=TIMEOUT,
        )
        end = r.json() if r.status_code == 200 else {}
        score = end.get("final_score")
        if isinstance(score, dict):
            score_val = score.get("final_score") or score.get("score")
        else:
            score_val = score
        test("Invite end interview + score", r.status_code == 200 and score_val is not None, f"score={score_val}")

        r = requests.get(
            f"{BASE}/api/v1/interviews/sessions/{inv_session_id}/my-report",
            headers=inv_headers,
            timeout=60,
        )
        test("Invite candidate PDF report", r.status_code == 200 and r.content[:4] == b"%PDF")

        r = requests.get(
            f"{BASE}/api/v1/recruiter/sessions/{inv_session_id}/report",
            headers=rec_headers,
            timeout=60,
        )
        test("Recruiter PDF report for invite session", r.status_code == 200 and r.content[:4] == b"%PDF")

    # ── Proctoring endpoints ───────────────────────────────────────
    sid = inv_session_id or "live-test-session"
    r = requests.post(f"{BASE}/proctor/reset", json={"session_id": sid}, timeout=15)
    test("Proctor reset", r.status_code == 200)

    r = requests.get(f"{BASE}/proctor/warnings", timeout=15)
    test("Proctor warnings", r.status_code == 200)

    r = requests.get(f"{BASE}/proctor/integrity-report", timeout=15)
    test("Proctor integrity report", r.status_code == 200)

    # ── Recruiter dashboard list ───────────────────────────────────
    r = requests.get(f"{BASE}/api/v1/recruiter/sessions", headers=rec_headers, timeout=30)
    sessions = r.json().get("data", r.json())
    count = len(sessions) if isinstance(sessions, list) else 0
    test("Recruiter sessions list", r.status_code == 200, f"count={count}")

    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 50)
    passed = sum(1 for r in results if r.startswith("PASS"))
    failed = sum(1 for r in results if r.startswith("FAIL"))
    print(f"LIVE DEPLOY ({BASE})")
    print(f"FINAL: {passed} PASS | {failed} FAIL")
    if failed:
        print("\nFailed tests:")
        for line in results:
            if line.startswith("FAIL"):
                print(f"  {line}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
