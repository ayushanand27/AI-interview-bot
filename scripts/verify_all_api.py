"""Verify auth, interview flow, DB persistence, and proctor health."""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8080"
PDF = Path(__file__).resolve().parents[1] / "test_resume.pdf"
DB_PATH = Path(__file__).resolve().parents[1] / "interview_bot.db"


def truncate(s: str, max_len: int = 400) -> str:
    s = json.dumps(s) if not isinstance(s, str) else s
    return s if len(s) <= max_len else s[:max_len] + "..."


def main() -> None:
    email = f"verify_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    results: list[tuple[int, str, str, str]] = []

    try:
        with httpx.Client(timeout=120.0) as client:
            # 0 — server up
            try:
                h = client.get(f"{BASE}/health")
                if h.status_code != 200:
                    print(f"Server health failed: {h.status_code} {h.text}")
                    sys.exit(1)
            except httpx.ConnectError:
                print(f"Cannot connect to {BASE} — start uvicorn app.main:app --port 8080")
                sys.exit(1)

            # 1 — register
            r1 = client.post(
                f"{BASE}/api/v1/auth/register",
                json={
                    "full_name": "Verify User",
                    "email": email,
                    "password": password,
                    "role": "candidate",
                },
            )
            ok1 = r1.status_code == 201 and r1.json().get("success")
            results.append(
                (1, "Register new user", "PASS" if ok1 else "FAIL", truncate(r1.text))
            )
            if not ok1:
                print_report(results)
                sys.exit(1)

            # 2 — login
            r2 = client.post(
                f"{BASE}/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            body2 = r2.json()
            token = (body2.get("data") or {}).get("access_token")
            ok2 = r2.status_code == 200 and bool(token)
            results.append(
                (2, "Login and get JWT", "PASS" if ok2 else "FAIL", truncate(r2.text))
            )
            if not ok2:
                print_report(results)
                sys.exit(1)

            headers = {"Authorization": f"Bearer {token}"}

            if not PDF.is_file():
                results.append((3, "Create interview session", "SKIP", "test_resume.pdf missing"))
                print_report(results)
                sys.exit(1)

            # 3 — create session
            r3 = client.post(
                f"{BASE}/api/v1/interviews/sessions",
                data={
                    "role_title": "Backend Developer",
                    "experience_level": "mid",
                    "topic_focus": "Python",
                    "job_description": "Build REST APIs with FastAPI.",
                },
                files={"resume_pdf": ("resume.pdf", PDF.read_bytes(), "application/pdf")},
                headers=headers,
            )
            ok3 = r3.status_code == 201
            sid = r3.json().get("session_id") if ok3 else None
            results.append(
                (3, "Create interview session", "PASS" if ok3 else "FAIL", truncate(r3.text))
            )
            if not ok3 or not sid:
                print_report(results)
                sys.exit(1)

            # 4 — generate questions
            r4 = client.post(
                f"{BASE}/api/v1/interviews/sessions/{sid}/questions",
                json={"question_count": 1},
                headers=headers,
            )
            ok4 = r4.status_code == 200
            results.append(
                (4, "Generate questions", "PASS" if ok4 else "FAIL", truncate(r4.text))
            )
            if not ok4:
                print_report(results)
                sys.exit(1)

            # 5 — submit answer + judgment
            r5 = client.post(
                f"{BASE}/api/v1/interviews/sessions/{sid}/answers",
                json={
                    "answer": "I use FastAPI with async SQLAlchemy, Pydantic models, and dependency injection."
                },
                headers=headers,
            )
            body5 = r5.json() if r5.status_code == 200 else {}
            has_judgment = bool(
                body5.get("judgment")
                or body5.get("score") is not None
                or body5.get("answer_judgment")
            )
            ok5 = r5.status_code == 200 and (
                has_judgment or "complete" in r5.text.lower() or "score" in r5.text.lower()
            )
            results.append(
                (5, "Submit answer + judgment", "PASS" if ok5 else "FAIL", truncate(r5.text))
            )

            # 6 — end interview
            r6 = client.post(
                f"{BASE}/api/v1/interviews/sessions/{sid}/end",
                headers=headers,
            )
            body6 = r6.json() if r6.status_code == 200 else {}
            ok6 = r6.status_code == 200 and (
                body6.get("final_score") is not None
                or body6.get("status") == "completed"
                or "final" in r6.text.lower()
            )
            results.append(
                (6, "End interview + final score", "PASS" if ok6 else "FAIL", truncate(r6.text))
            )

            # 7 — DB check
            time.sleep(0.5)
            ok7 = False
            db_msg = "DB file not found"
            if DB_PATH.is_file():
                conn = sqlite3.connect(DB_PATH)
                row = conn.execute(
                    "SELECT session_id, status, final_score FROM sessions WHERE session_id = ?",
                    (sid.replace("-", ""),),
                ).fetchone()
                if not row:
                    row = conn.execute(
                        "SELECT session_id, status, final_score FROM sessions WHERE session_id = ?",
                        (sid,),
                    ).fetchone()
                conn.close()
                ok7 = row is not None
                db_msg = str(row) if row else "No row for session_id"
            results.append((7, "Session in interview_bot.db", "PASS" if ok7 else "FAIL", db_msg))

            # 8 — proctor health
            r8 = client.get(f"{BASE}/proctor/health")
            ok8 = r8.status_code == 200
            results.append(
                (8, "Proctor /proctor/health", "PASS" if ok8 else "FAIL", truncate(r8.text))
            )

            # unused headers but validates token path exists
            _ = headers

    except Exception as exc:
        print(f"Verification error: {exc}")
        sys.exit(1)

    print_report(results)
    failed = [r for r in results if r[2] == "FAIL"]
    sys.exit(1 if failed else 0)


def print_report(results: list[tuple[int, str, str, str]]) -> None:
    print("\n=== API Verification Report ===\n")
    for num, label, status, response in results:
        print(f"{num}. {label}: {status}")
        print(f"   Response: {response}\n")


if __name__ == "__main__":
    main()
