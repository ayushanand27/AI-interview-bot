#!/usr/bin/env python3
"""Run live API tests against local server."""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8080"
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "interview_bot.db"
RESUME = ROOT / "test_resume.pdf"

results: list[dict] = []
state: dict = {}


def record(test: str, passed: bool, summary: str, notes: str = "") -> None:
    results.append({"test": test, "passed": passed, "summary": summary, "notes": notes})
    status = "PASS" if passed else "FAIL"
    print(f"\n{'='*60}\n{test}: {status}\n{summary}")
    if notes:
        print(f"Notes: {notes}")


def get_verification_token(email: str) -> str | None:
    if not DB.exists():
        return None
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "SELECT verification_token FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_reset_token(email: str) -> str | None:
    if not DB.exists():
        return None
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "SELECT reset_token FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def main() -> int:
    candidate_email = "testcandidate123@example.com"
    recruiter_email = "testrecruiter123@example.com"
    password = "password123"

    # TEST 1
    try:
        r1 = requests.get(f"{BASE}/health", timeout=15)
        r2 = requests.get(f"{BASE}/api/v1/status", timeout=15)
        ok = r1.status_code == 200 and r2.status_code == 200
        record(
            "TEST 1 - Health Check",
            ok,
            f"/health={r1.status_code} {r1.json()} | /status={r2.status_code} keys={list(r2.json().keys())}",
        )
    except Exception as e:
        record("TEST 1 - Health Check", False, str(e))
        return 1

    # TEST 2
    try:
        r = requests.post(
            f"{BASE}/api/v1/auth/register",
            json={
                "full_name": "Test Candidate",
                "email": candidate_email,
                "password": password,
                "role": "candidate",
            },
            timeout=30,
        )
        body = r.json()
        ok = r.status_code in (201, 409)
        msg = body.get("message", body)
        verify_token_db = get_verification_token(candidate_email)
        record(
            "TEST 2 - Register candidate",
            ok and (r.status_code == 201 or "already" in str(msg).lower()),
            f"HTTP {r.status_code} | message={msg}",
            f"verification_token in DB: {'yes' if verify_token_db else 'no (may already exist)'}",
        )
        if verify_token_db:
            state["verify_token"] = verify_token_db
    except Exception as e:
        record("TEST 2 - Register candidate", False, str(e))

    # TEST 3 - login (may need new password after reset)
    access_token = None
    for pwd in [password, "newpassword123"]:
        try:
            r = requests.post(
                f"{BASE}/api/v1/auth/login",
                json={"email": candidate_email, "password": pwd},
                timeout=15,
            )
            if r.status_code == 200:
                access_token = r.json()["data"]["access_token"]
                state["password"] = pwd
                break
        except Exception:
            pass
    record(
        "TEST 3 - Login",
        access_token is not None,
        f"token={'obtained' if access_token else 'missing'} (password used: {state.get('password', 'n/a')})",
    )
    state["access_token"] = access_token

    # TEST 4
    try:
        token = state.get("verify_token") or get_verification_token(candidate_email)
        if not token:
            record("TEST 4 - Verify email", False, "No verification token in DB")
        else:
            r = requests.get(
                f"{BASE}/api/v1/auth/verify-email",
                params={"token": token},
                timeout=15,
            )
            body = r.json()
            ok = r.status_code == 200 and body.get("success") is True
            record(
                "TEST 4 - Verify email",
                ok,
                f"HTTP {r.status_code} | {body}",
                "If already verified, token may be cleared — check is_verified in DB",
            )
    except Exception as e:
        record("TEST 4 - Verify email", False, str(e))

    # TEST 5
    try:
        r = requests.post(
            f"{BASE}/api/v1/auth/forgot-password",
            json={"email": candidate_email},
            timeout=30,
        )
        body = r.json()
        reset_token = get_reset_token(candidate_email)
        ok = r.status_code == 200
        record(
            "TEST 5 - Forgot password",
            ok,
            f"HTTP {r.status_code} | {body}",
            f"reset_token in DB: {'yes' if reset_token else 'no'}",
        )
        if reset_token:
            state["reset_token"] = reset_token
    except Exception as e:
        record("TEST 5 - Forgot password", False, str(e))

    # TEST 6
    try:
        token = state.get("reset_token") or get_reset_token(candidate_email)
        if not token:
            record("TEST 6 - Reset password", False, "No reset token in DB")
        else:
            r = requests.post(
                f"{BASE}/api/v1/auth/reset-password",
                json={"token": token, "new_password": "newpassword123"},
                timeout=15,
            )
            body = r.json()
            ok = r.status_code == 200 and "reset" in body.get("message", "").lower()
            record("TEST 6 - Reset password", ok, f"HTTP {r.status_code} | {body}")
            # Re-login with new password
            lr = requests.post(
                f"{BASE}/api/v1/auth/login",
                json={"email": candidate_email, "password": "newpassword123"},
                timeout=15,
            )
            if lr.status_code == 200:
                state["access_token"] = lr.json()["data"]["access_token"]
    except Exception as e:
        record("TEST 6 - Reset password", False, str(e))

    headers = {"Authorization": f"Bearer {state.get('access_token')}"}

    # TEST 7 - multipart session
    session_id = None
    try:
        if not state.get("access_token"):
            record("TEST 7 - Create session", False, "No access token")
        elif not RESUME.exists():
            record("TEST 7 - Create session", False, f"Missing {RESUME}")
        else:
            with RESUME.open("rb") as f:
                r = requests.post(
                    f"{BASE}/api/v1/interviews/sessions",
                    headers=headers,
                    data={
                        "role_title": "Python Developer",
                        "experience_level": "mid",
                        "topic_focus": "FastAPI",
                        "job_description": "Python developer with FastAPI experience required.",
                    },
                    files={"resume_pdf": ("test_resume.pdf", f, "application/pdf")},
                    timeout=60,
                )
            body = r.json()
            session_id = body.get("session_id")
            ok = r.status_code in (200, 201) and bool(session_id)
            record(
                "TEST 7 - Create session",
                ok,
                f"HTTP {r.status_code} | session_id={session_id}",
                "Endpoint requires multipart form + resume PDF (not JSON)",
            )
            state["session_id"] = session_id
    except Exception as e:
        record("TEST 7 - Create session", False, str(e))

    sid = state.get("session_id")

    # TEST 8
    try:
        if not sid:
            record("TEST 8 - Generate questions", False, "No session_id")
        else:
            r = requests.post(
                f"{BASE}/api/v1/interviews/sessions/{sid}/questions",
                headers=headers,
                json={"question_count": 2},
                timeout=120,
            )
            body = r.json()
            ok = r.status_code == 200 and (
                body.get("total_questions") == 2 or "question" in str(body).lower()
            )
            record("TEST 8 - Generate questions", ok, f"HTTP {r.status_code} | {json.dumps(body)[:300]}")
    except Exception as e:
        record("TEST 8 - Generate questions", False, str(e))

    # TEST 9
    try:
        if not sid:
            record("TEST 9 - Current question", False, "No session_id")
        else:
            r = requests.get(
                f"{BASE}/api/v1/interviews/sessions/{sid}/current-question",
                headers=headers,
                timeout=30,
            )
            body = r.json()
            q = body.get("question") or body.get("data", {})
            ok = r.status_code == 200 and bool(body.get("question") or body.get("question_index") is not None)
            record(
                "TEST 9 - Current question",
                ok,
                f"HTTP {r.status_code} | index={body.get('question_index')} has_question={bool(body.get('question'))}",
            )
    except Exception as e:
        record("TEST 9 - Current question", False, str(e))

    # TEST 10
    try:
        if not sid:
            record("TEST 10 - Submit answer", False, "No session_id")
        else:
            r = requests.post(
                f"{BASE}/api/v1/interviews/sessions/{sid}/answers",
                headers=headers,
                json={
                    "answer": "FastAPI is a modern Python web framework that uses async by default and provides automatic OpenAPI documentation."
                },
                timeout=120,
            )
            body = r.json()
            ok = r.status_code == 200
            record(
                "TEST 10 - Submit answer",
                ok,
                f"HTTP {r.status_code} | keys={list(body.keys())[:8]} is_complete={body.get('is_complete')}",
            )
            # second answer if needed
            if ok and not body.get("is_complete"):
                r2 = requests.post(
                    f"{BASE}/api/v1/interviews/sessions/{sid}/answers",
                    headers=headers,
                    json={
                        "answer": "I use dependency injection, Pydantic models, and async routes for scalable APIs."
                    },
                    timeout=120,
                )
                record(
                    "TEST 10b - Submit answer 2",
                    r2.status_code == 200,
                    f"HTTP {r2.status_code} | is_complete={r2.json().get('is_complete')}",
                )
    except Exception as e:
        record("TEST 10 - Submit answer", False, str(e))

    # TEST 11
    try:
        if not sid:
            record("TEST 11 - End interview", False, "No session_id")
        else:
            r = requests.post(
                f"{BASE}/api/v1/interviews/sessions/{sid}/end",
                headers=headers,
                timeout=120,
            )
            body = r.json()
            ok = r.status_code == 200 and (
                "final_score" in body or body.get("final_score") is not None
            )
            record(
                "TEST 11 - End interview",
                ok,
                f"HTTP {r.status_code} | final_score={body.get('final_score')} recommendation={body.get('recommendation')}",
            )
    except Exception as e:
        record("TEST 11 - End interview", False, str(e))

    # TEST 12
    try:
        if not sid:
            record("TEST 12 - Candidate report", False, "No session_id")
        else:
            r = requests.get(
                f"{BASE}/api/v1/interviews/sessions/{sid}/my-report",
                headers=headers,
                timeout=60,
            )
            out = ROOT / "test_candidate_report.pdf"
            ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf")
            if ok:
                out.write_bytes(r.content)
            record(
                "TEST 12 - Candidate report",
                ok,
                f"HTTP {r.status_code} | size={len(r.content)} bytes saved={out.name}",
            )
    except Exception as e:
        record("TEST 12 - Candidate report", False, str(e))

    # TEST 13
    try:
        r = requests.get(f"{BASE}/proctor/health", timeout=15)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
        ok = r.status_code == 200
        record("TEST 13 - Proctor health", ok, f"HTTP {r.status_code} | {body}")
    except Exception as e:
        record("TEST 13 - Proctor health", False, str(e))

    # TEST 14
    try:
        r = requests.post(
            f"{BASE}/proctor/analyze",
            json={"session_id": "test123", "frame_base64": ""},
            timeout=30,
        )
        ok = r.status_code in (200, 400, 422)
        record(
            "TEST 14 - Proctor analyze",
            ok,
            f"HTTP {r.status_code} | {r.text[:200]}",
        )
    except Exception as e:
        record("TEST 14 - Proctor analyze", False, str(e))

    # TEST 15
    try:
        r = requests.post(
            f"{BASE}/api/v1/auth/register",
            json={
                "full_name": "Test Recruiter",
                "email": recruiter_email,
                "password": password,
                "role": "recruiter",
            },
            timeout=30,
        )
        ok = r.status_code in (201, 409)
        record(
            "TEST 15 - Register recruiter",
            ok,
            f"HTTP {r.status_code} | {r.json().get('message', r.text[:200])}",
        )
    except Exception as e:
        record("TEST 15 - Register recruiter", False, str(e))

    # TEST 16
    recruiter_token = None
    try:
        r = requests.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": recruiter_email, "password": password},
            timeout=15,
        )
        ok = r.status_code == 200
        if ok:
            recruiter_token = r.json()["data"]["access_token"]
        record(
            "TEST 16 - Recruiter login",
            ok,
            f"HTTP {r.status_code} | token={'yes' if recruiter_token else 'no'}",
        )
        state["recruiter_token"] = recruiter_token
    except Exception as e:
        record("TEST 16 - Recruiter login", False, str(e))

    rh = {"Authorization": f"Bearer {recruiter_token}"}

    # TEST 17
    try:
        r = requests.get(f"{BASE}/api/v1/recruiter/sessions", headers=rh, timeout=30)
        body = r.json()
        ok = r.status_code == 200
        data = body.get("data", body)
        count = len(data) if isinstance(data, list) else "n/a"
        record(
            "TEST 17 - Recruiter sessions",
            ok,
            f"HTTP {r.status_code} | sessions_count={count}",
        )
    except Exception as e:
        record("TEST 17 - Recruiter sessions", False, str(e))

    # TEST 18
    invite_token = None
    try:
        r = requests.post(
            f"{BASE}/api/v1/recruiter/create-assessment",
            headers=rh,
            json={
                "jd_text": "We need a Python developer with FastAPI experience",
                "question_count": 2,
                "difficulty": "medium",
                "expiry_hours": 48,
            },
            timeout=120,
        )
        body = r.json()
        ok = r.status_code == 200
        data = body.get("data", body)
        invite_token = data.get("token") if isinstance(data, dict) else None
        record(
            "TEST 18 - Create assessment",
            ok and bool(invite_token),
            f"HTTP {r.status_code} | token={invite_token} link={data.get('invite_link') if isinstance(data, dict) else None}",
        )
        state["invite_token"] = invite_token
    except Exception as e:
        record("TEST 18 - Create assessment", False, str(e))

    # TEST 19
    try:
        token = state.get("invite_token")
        if not token:
            record("TEST 19 - Validate invite", False, "No invite token")
        else:
            r = requests.get(f"{BASE}/api/v1/invite/{token}", timeout=30)
            body = r.json()
            ok = r.status_code == 200 and body.get("valid") is True
            record(
                "TEST 19 - Validate invite",
                ok,
                f"HTTP {r.status_code} | valid={body.get('valid')} role={body.get('role_title')}",
            )
    except Exception as e:
        record("TEST 19 - Validate invite", False, str(e))

    # TEST 20
    try:
        if not sid:
            record("TEST 20 - Recruiter report", False, "No session_id")
        else:
            r = requests.get(
                f"{BASE}/api/v1/recruiter/sessions/{sid}/report",
                headers=rh,
                timeout=60,
            )
            out = ROOT / "test_recruiter_report.pdf"
            ok = r.status_code == 200 and len(r.content) > 100
            if ok:
                out.write_bytes(r.content)
            record(
                "TEST 20 - Recruiter report",
                ok,
                f"HTTP {r.status_code} | size={len(r.content)} bytes",
            )
    except Exception as e:
        record("TEST 20 - Recruiter report", False, str(e))

    # TEST 21
    try:
        conn = sqlite3.connect(DB)
        users = conn.execute(
            "SELECT id, email, role, is_verified FROM users ORDER BY id DESC LIMIT 5"
        ).fetchall()
        sessions = conn.execute(
            "SELECT session_id, status, role_title, final_score FROM sessions ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        invites = conn.execute(
            "SELECT token, difficulty, expiry_at, used_count FROM interview_invites ORDER BY created_at DESC LIMIT 3"
        ).fetchall()
        conn.close()
        record(
            "TEST 21 - Database check",
            True,
            f"users={len(users)} sessions={len(sessions)} invites={len(invites)}",
            f"latest users: {users[:2]} | latest session: {sessions[0] if sessions else None}",
        )
    except Exception as e:
        record("TEST 21 - Database check", False, str(e))

    # Summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if r["passed"])
    print(f"Passed: {passed}/{len(results)}\n")
    for r in results:
        print(f"{r['test']}: {'PASS' if r['passed'] else 'FAIL'} — {r['summary'][:120]}")

    out = ROOT / "scripts" / "api_test_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
