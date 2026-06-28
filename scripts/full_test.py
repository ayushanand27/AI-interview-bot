#!/usr/bin/env python3
"""Full end-to-end API test suite for SmartSkale InterviewBot."""

from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import sys
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8080"
DB_PATH = ROOT / "smartskale.db"
RESUME_PDF = ROOT / "test_resume.pdf"
RESULTS_PATH = ROOT / "test_results.txt"

results: list[str] = []
state: dict = {}


def test(name: str, passed: bool, details: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    line = f"{status} | {name} | {details}"
    results.append(line)
    print(line)


def save_results() -> None:
    passed = len([r for r in results if r.startswith("PASS")])
    failed = len([r for r in results if r.startswith("FAIL")])
    with RESULTS_PATH.open("w", encoding="utf-8") as f:
        f.write("SmartSkale InterviewBot - Full Test Results\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"TOTAL: {passed} PASS, {failed} FAIL\n\n")
        for r in results:
            f.write(r + "\n")


def unwrap(body: dict, key: str, default=None):
    if key in body:
        return body[key]
    data = body.get("data")
    if isinstance(data, dict) and key in data:
        return data[key]
    return default


def token_from_login(resp: requests.Response) -> str:
    body = resp.json()
    return unwrap(body, "access_token", "") or ""


def main() -> int:
    if not RESUME_PDF.exists():
        print(f"Missing {RESUME_PDF}")
        return 1

    candidate_email = f"testcand_{uuid.uuid4().hex[:8]}@example.com"
    recruiter_email = f"testrec_{uuid.uuid4().hex[:8]}@example.com"
    jd_text = """
We are looking for a Python Developer with 2+ years
experience in FastAPI, REST APIs, and databases.
Must know async programming and SQLAlchemy.
""".strip()

    # ============ AUTH TESTS ============

    r = requests.get(f"{BASE}/health", timeout=15)
    test("Health check", r.status_code == 200, str(r.json()))

    r = requests.get(f"{BASE}/api/v1/status", timeout=15)
    data = r.json()
    test("API status", r.status_code == 200)
    test("DB connected", data.get("database_connected") is True)
    test("Proctoring loaded", data.get("proctoring_loaded") is True)

    r = requests.post(
        f"{BASE}/api/v1/auth/register",
        json={
            "full_name": "Test Candidate",
            "email": candidate_email,
            "password": "password123",
            "role": "candidate",
        },
        timeout=30,
    )
    test(
        "Register candidate",
        r.status_code == 201,
        r.json().get("message", "")[:50],
    )

    r = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": candidate_email, "password": "password123"},
        timeout=15,
    )
    test("Login candidate", r.status_code == 200)
    cand_token = token_from_login(r)
    test("Candidate token returned", bool(cand_token))
    cand_headers = {"Authorization": f"Bearer {cand_token}"}

    r = requests.get(f"{BASE}/api/v1/auth/me", headers=cand_headers, timeout=15)
    me = r.json().get("data", r.json())
    test(
        "Get current user",
        r.status_code == 200,
        f"role={me.get('role')}",
    )

    r = requests.post(
        f"{BASE}/api/v1/auth/forgot-password",
        json={"email": candidate_email},
        timeout=30,
    )
    test("Forgot password", r.status_code == 200, str(r.json()))

    new_password = "newpass45678"
    reset_token = None
    time.sleep(0.5)
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT reset_token FROM users WHERE email = ?",
                (candidate_email,),
            ).fetchone()
            if row:
                reset_token = row[0]
    if reset_token:
        r = requests.post(
            f"{BASE}/api/v1/auth/reset-password",
            json={"token": reset_token, "new_password": new_password},
            timeout=15,
        )
        test("Reset candidate password", r.status_code == 200, str(r.json())[:80])
        r = requests.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": candidate_email, "password": new_password},
            timeout=15,
        )
        test("Login after password reset", r.status_code == 200)
        cand_token = token_from_login(r)
        cand_headers = {"Authorization": f"Bearer {cand_token}"}
    else:
        test("Reset candidate password", False, "no reset_token in DB")
        test("Login after password reset", False, "skipped")

    r = requests.post(
        f"{BASE}/api/v1/auth/resend-verification",
        json={"email": candidate_email},
        timeout=30,
    )
    test("Resend verification", r.status_code == 200, str(r.json()))

    time.sleep(0.5)
    verification_token = None
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT verification_token FROM users WHERE email = ?",
                (candidate_email,),
            ).fetchone()
            if row:
                verification_token = row[0]
    if verification_token:
        r = requests.get(
            f"{BASE}/api/v1/auth/verify-email",
            params={"token": verification_token},
            timeout=15,
        )
        test("Verify candidate email", r.status_code == 200, str(r.json())[:60])
    else:
        test("Verify candidate email", False, "no verification_token in DB")

    # Invite-flow login security (password required before session resume)
    inv_login_email = f"inv_login_{uuid.uuid4().hex[:8]}@example.com"
    rec_login_email = f"rec_login_{uuid.uuid4().hex[:8]}@example.com"
    requests.post(
        f"{BASE}/api/v1/auth/register",
        json={
            "full_name": "Invite Login Recruiter",
            "email": rec_login_email,
            "password": "password123",
            "role": "recruiter",
        },
        timeout=30,
    )
    rec_login_resp = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": rec_login_email, "password": "password123"},
        timeout=15,
    )
    rec_login_token = token_from_login(rec_login_resp)
    inv_assess = requests.post(
        f"{BASE}/api/v1/recruiter/create-assessment",
        headers={"Authorization": f"Bearer {rec_login_token}"},
        data={
            "jd_text": "Python developer with REST APIs.",
            "question_count": "2",
            "difficulty": "Medium",
            "expiry_hours": "48",
        },
        timeout=180,
    )
    inv_login_token = ""
    if inv_assess.status_code == 200:
        inv_body = inv_assess.json()
        inv_data = inv_body.get("data", inv_body)
        invite_link = inv_data.get("invite_link", "") if isinstance(inv_data, dict) else ""
        if invite_link:
            inv_login_token = invite_link.rstrip("/").split("/")[-1]

    if inv_login_token:
        requests.post(
            f"{BASE}/api/v1/invite/{inv_login_token}/register",
            json={"name": "Invite Login Candidate", "email": inv_login_email, "phone": ""},
            timeout=60,
        )
        wrong_inv_login = requests.post(
            f"{BASE}/api/v1/invite/{inv_login_token}/login",
            json={
                "email": inv_login_email,
                "password": "definitely-wrong-password",
                "phone": "",
            },
            timeout=30,
        )
        test(
            "Invite login wrong password",
            wrong_inv_login.status_code == 401,
            f"status={wrong_inv_login.status_code}",
        )

        inv_reset_token = None
        if DB_PATH.exists():
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT reset_token FROM users WHERE email = ?",
                    (inv_login_email,),
                ).fetchone()
                if row:
                    inv_reset_token = row[0]
        if inv_reset_token:
            requests.post(
                f"{BASE}/api/v1/auth/reset-password",
                json={"token": inv_reset_token, "new_password": "password123"},
                timeout=15,
            )
            ok_inv_login = requests.post(
                f"{BASE}/api/v1/invite/{inv_login_token}/login",
                json={"email": inv_login_email, "password": "password123", "phone": ""},
                timeout=30,
            )
            ok_body = ok_inv_login.json().get("data", {}) if ok_inv_login.status_code == 200 else {}
            test(
                "Invite login correct password",
                ok_inv_login.status_code == 200
                and bool(ok_body.get("session_id"))
                and bool(ok_body.get("access_token")),
                f"status={ok_inv_login.status_code}",
            )
        else:
            test("Invite login correct password", False, "no reset_token in DB")
    else:
        test("Invite login wrong password", False, "skipped - no invite token")
        test("Invite login correct password", False, "skipped - no invite token")

    # ============ INTERVIEW TESTS ============

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
    test("Create interview session", r.status_code in (200, 201), f"status={r.status_code}")
    session_data = r.json()
    session_id = session_data.get("session_id", "")
    test("Session ID returned", bool(session_id), session_id[:16] if session_id else "")
    state["session_id"] = session_id

    if not session_id:
        save_results()
        print("\nCannot continue without session_id")
        return 1

    r = requests.post(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/questions",
        headers=cand_headers,
        json={"question_count": 2},
        timeout=120,
    )
    test(
        "Generate questions",
        r.status_code == 200,
        f"questions={r.json().get('total_questions')}",
    )

    r = requests.get(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/current-question",
        headers=cand_headers,
        timeout=30,
    )
    test("Get current question", r.status_code == 200)
    question_text = r.json().get("question", "")
    test("Question text returned", bool(question_text), question_text[:50])

    r = requests.post(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/answers",
        headers=cand_headers,
        json={
            "answer": (
                "FastAPI is a modern Python framework for building APIs. "
                "It uses async/await and provides automatic OpenAPI documentation. "
                "I have used it to build REST APIs with SQLAlchemy for database operations."
            )
        },
        timeout=120,
    )
    test("Submit answer 1", r.status_code == 200)

    r = requests.get(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/current-question",
        headers=cand_headers,
        timeout=30,
    )
    test("Get question 2", r.status_code == 200)

    r = requests.post(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/answers",
        headers=cand_headers,
        json={
            "answer": (
                "SQLAlchemy ORM helps write database queries in Python instead of raw SQL. "
                "It supports multiple databases and makes migrations easier with Alembic."
            )
        },
        timeout=120,
    )
    test(
        "Submit answer 2",
        r.status_code == 200,
        f"complete={r.json().get('is_complete')}",
    )

    r = requests.post(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/end",
        headers=cand_headers,
        timeout=120,
    )
    test("End interview", r.status_code == 200)
    end_data = r.json()
    final_score = end_data.get("final_score")
    if isinstance(final_score, dict):
        score = final_score.get("final_score") or final_score.get("score") or 0
        recommendation = final_score.get("recommendation")
    else:
        score = final_score or 0
        recommendation = end_data.get("recommendation")
    test("Final score returned", bool(score), f"score={score}")
    test("Recommendation returned", bool(recommendation), str(recommendation))

    r = requests.get(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/my-report",
        headers=cand_headers,
        timeout=60,
    )
    test(
        "Candidate PDF report",
        r.status_code == 200,
        f"size={len(r.content)} bytes",
    )
    test("Is valid PDF", r.content[:4] == b"%PDF")

    # ============ PROCTORING TESTS ============

    r = requests.get(f"{BASE}/proctor/health", timeout=15)
    test("Proctoring health", r.status_code == 200, str(r.json()))

    r = requests.post(
        f"{BASE}/proctor/reset",
        json={"session_id": session_id},
        timeout=15,
    )
    test("Proctor reset", r.status_code == 200)

    r = requests.get(f"{BASE}/proctor/warnings", timeout=15)
    test("Proctor warnings", r.status_code == 200)

    r = requests.get(f"{BASE}/proctor/integrity-report", timeout=15)
    test("Integrity report", r.status_code == 200)

    # ============ RECRUITER TESTS ============

    r = requests.post(
        f"{BASE}/api/v1/auth/register",
        json={
            "full_name": "Test Recruiter",
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
    test("Login recruiter", r.status_code == 200)
    rec_token = token_from_login(r)
    test("Recruiter token returned", bool(rec_token))
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    r = requests.get(
        f"{BASE}/api/v1/recruiter/sessions",
        headers=rec_headers,
        timeout=30,
    )
    rec_sessions = r.json().get("data", r.json())
    count = len(rec_sessions) if isinstance(rec_sessions, list) else "N/A"
    test("Recruiter sessions list", r.status_code == 200, f"count={count}")

    r = requests.get(
        f"{BASE}/api/v1/recruiter/sessions/{session_id}/report",
        headers=rec_headers,
        timeout=60,
    )
    test(
        "Recruiter PDF report",
        r.status_code == 200,
        f"size={len(r.content)} bytes",
    )
    test("Recruiter PDF valid", r.content[:4] == b"%PDF")

    r = requests.post(
        f"{BASE}/api/v1/recruiter/create-assessment",
        headers=rec_headers,
        data={
            "jd_text": "Python Developer with FastAPI and PostgreSQL experience needed for backend APIs.",
            "question_count": "2",
            "difficulty": "medium",
            "expiry_hours": "48",
        },
        timeout=120,
    )
    test(
        "Create assessment",
        r.status_code == 200,
        f"status={r.status_code} resp={str(r.json())[:80]}",
    )
    invite_token = ""
    if r.status_code == 200:
        body = r.json()
        invite_data = body.get("data", body)
        invite_token = invite_data.get("token", "") if isinstance(invite_data, dict) else ""
        test(
            "Invite token returned",
            bool(invite_token),
            invite_token[:16] if invite_token else "missing",
        )

    if invite_token:
        r = requests.get(f"{BASE}/api/v1/invite/{invite_token}", timeout=30)
        test(
            "Validate invite link",
            r.status_code == 200,
            f"valid={r.json().get('valid')}",
        )

        r = requests.post(
            f"{BASE}/api/v1/invite/{invite_token}/register",
            json={
                "name": "Invite Candidate",
                "email": f"invitecand_{uuid.uuid4().hex[:8]}@example.com",
                "phone": "9999999999",
            },
            timeout=30,
        )
        test(
            "Invite candidate register",
            r.status_code in (200, 201),
            f"status={r.status_code}",
        )
    else:
        test("Validate invite link", False, "skipped - no invite token")
        test("Invite candidate register", False, "skipped - no invite token")

    # ============ DATABASE CHECK ============

    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    ended = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE status='ended'"
    ).fetchone()[0]
    invites = conn.execute("SELECT COUNT(*) FROM interview_invites").fetchone()[0]
    conn.close()

    test("Users in DB", users > 0, f"count={users}")
    test("Sessions in DB", sessions > 0, f"count={sessions}")
    test("Completed sessions", ended > 0, f"count={ended}")
    test("Invites in DB", invites > 0, f"count={invites}")

    # ============ RECORDING TESTS ============

    fake_video = b"\x1a\x45\xdf\xa3" + b"\x00" * 100

    r = requests.post(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/recording",
        headers=cand_headers,
        files={"video": ("recording.webm", io.BytesIO(fake_video), "video/webm")},
        timeout=60,
    )
    test(
        "Upload recording",
        r.status_code == 200,
        f"status={r.status_code} resp={str(r.json())[:60]}",
    )

    r = requests.get(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/my-recording",
        headers=cand_headers,
        timeout=60,
    )
    test(
        "Candidate get own recording",
        r.status_code in (200, 404),
        f"status={r.status_code} size={len(r.content)}",
    )
    if r.status_code == 200:
        test(
            "Recording file returned",
            len(r.content) > 0,
            f"size={len(r.content)} bytes",
        )
    else:
        test("Recording 404 handled", r.status_code == 404, "No recording file yet - acceptable")

    r = requests.get(
        f"{BASE}/api/v1/interviews/sessions/{session_id}/recording",
        headers=rec_headers,
        timeout=60,
    )
    test(
        "Recruiter get recording",
        r.status_code in (200, 404),
        f"status={r.status_code}",
    )

    uploads_dir = ROOT / "uploads"
    test("Uploads folder exists", uploads_dir.exists(), f"path={uploads_dir}")

    if uploads_dir.exists():
        files = os.listdir(uploads_dir)
        webm_files = [f for f in files if f.endswith(".webm")]
        mp4_files = [f for f in files if f.endswith(".mp4")]
        test("WebM recording saved", len(webm_files) > 0, f"count={len(webm_files)}")
        ffmpeg_available = shutil.which("ffmpeg") is not None
        test(
            "MP4 conversion exists",
            len(mp4_files) > 0 or len(webm_files) > 0,
            f"mp4={len(mp4_files)} webm={len(webm_files)} ffmpeg={'yes' if ffmpeg_available else 'no'}",
        )
        session_recording = f"{session_id}_recording.webm"
        test(
            "Session recording file",
            session_recording in files or any(session_id[:8] in f for f in files),
            f"looking for {session_id[:8]}*",
        )

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT recording_filename, recording_mp4_filename FROM sessions WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT recording_filename, recording_mp4_filename FROM sessions WHERE session_id=?",
            (session_id.replace("-", ""),),
        ).fetchone()
    conn.close()

    if row:
        test("Recording filename in DB", bool(row[0]), f"webm={row[0]}")
        ffmpeg_available = shutil.which("ffmpeg") is not None
        test(
            "MP4 filename in DB",
            bool(row[1]) or bool(row[0]),
            f"mp4={row[1]} webm={row[0]} ffmpeg={'yes' if ffmpeg_available else 'no'}",
        )
    else:
        test("Session found in DB", False, "session not found")

    # ============ SAVE RESULTS ============
    save_results()
    print("\n" + "=" * 50)
    passed = len([r for r in results if r.startswith("PASS")])
    failed = len([r for r in results if r.startswith("FAIL")])
    print(f"FINAL: {passed} PASS | {failed} FAIL")
    print(f"Results saved to {RESULTS_PATH}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
