"""Run the full interview API flow and print session_id."""
import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
PDF = Path(__file__).resolve().parents[1] / "test_resume.pdf"


def main() -> None:
    if not PDF.is_file():
        print("Missing test_resume.pdf", file=sys.stderr)
        sys.exit(1)

    with httpx.Client(timeout=120.0) as client:
        r1 = client.post(
            f"{BASE}/api/v1/interviews/sessions",
            data={
                "role_title": "Backend Developer",
                "experience_level": "mid",
                "topic_focus": "Python",
                "job_description": "Build REST APIs with FastAPI and SQLAlchemy.",
            },
            files={"resume_pdf": ("resume.pdf", PDF.read_bytes(), "application/pdf")},
        )
        r1.raise_for_status()
        session = r1.json()
        sid = session["session_id"]
        print("1. create session:", sid, "status", session["status"])

        r2 = client.post(
            f"{BASE}/api/v1/interviews/sessions/{sid}/questions",
            json={"question_count": 1},
        )
        r2.raise_for_status()
        print("2. generate questions:", r2.json().get("total_questions"), "questions")

        r3 = client.get(f"{BASE}/api/v1/interviews/sessions/{sid}/current-question")
        r3.raise_for_status()
        q = r3.json()
        print("3. current question:", (q.get("question") or "")[:80], "...")

        r4 = client.post(
            f"{BASE}/api/v1/interviews/sessions/{sid}/answers",
            json={"answer": "I would use FastAPI with async SQLAlchemy and Alembic migrations."},
        )
        r4.raise_for_status()
        print("4. submit answer:", r4.json().get("message", "")[:80])

        r5 = client.post(f"{BASE}/api/v1/interviews/sessions/{sid}/end")
        r5.raise_for_status()
        end = r5.json()
        print("5. end interview:", end["status"], "answered", end["answered_count"])

    print("SESSION_ID=" + sid)


if __name__ == "__main__":
    main()
