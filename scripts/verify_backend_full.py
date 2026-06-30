"""Full backend verification (Tests 1-7) against http://127.0.0.1:8080."""
from __future__ import annotations

import json
import sqlite3
import struct
import sys
import uuid
import wave
from io import BytesIO
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8080"
ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "test_resume.pdf"
DB_PATH = ROOT / "interview_bot.db"


def jdump(obj, max_len: int = 1200) -> str:
    if isinstance(obj, (dict, list)):
        s = json.dumps(obj, default=str)
    else:
        s = str(obj)
    return s if len(s) <= max_len else s[:max_len] + "..."


def make_test_wav() -> bytes:
    """Minimal 16kHz mono WAV (~1s tone) for upload smoke test."""
    sample_rate = 16000
    duration = 1.0
    freq = 440.0
    n = int(sample_rate * duration)
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n):
            val = int(8000 * __import__("math").sin(2 * 3.14159265 * freq * i / sample_rate))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))
    return buf.getvalue()


def try_speech_wav() -> bytes:
    """Windows SAPI one-line speech if available."""
    out = ROOT / "scripts" / "_test_speech.wav"
    try:
        import subprocess

        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{out.as_posix().replace('/', chr(92))}'); "
            "$s.Speak('I use FastAPI with async SQLAlchemy for REST APIs.'); "
            "$s.Dispose()"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=30,
            check=True,
        )
        if out.is_file() and out.stat().st_size > 1000:
            return out.read_bytes()
    except Exception:
        pass
    return make_test_wav()


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.response: str = ""
        self.error: str = ""
        self.fix: str = ""


def main() -> int:
    results: list[TestResult] = []
    email = f"verify_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    token = ""
    sid = ""
    end_body: dict = {}

    client = httpx.Client(timeout=180.0, follow_redirects=True)

    # --- TEST 1 Auth ---
    t1 = TestResult("TEST 1 - Auth")
    try:
        r_reg = client.post(
            f"{BASE}/api/v1/auth/register",
            json={
                "full_name": "Verify User",
                "email": email,
                "password": password,
                "role": "candidate",
            },
        )
        r_log = client.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        body_log = r_log.json()
        token = (body_log.get("data") or {}).get("access_token") or ""
        r_me = client.get(
            f"{BASE}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        t1.response = jdump(
            {
                "register": {"status": r_reg.status_code, "body": r_reg.json()},
                "login": {"status": r_log.status_code, "has_token": bool(token)},
                "me": {"status": r_me.status_code, "body": r_me.json()},
            }
        )
        t1.passed = (
            r_reg.status_code == 201
            and r_log.status_code == 200
            and bool(token)
            and r_me.status_code == 200
            and (r_me.json().get("data") or {}).get("email") == email
        )
        if not t1.passed:
            t1.error = f"register={r_reg.status_code} login={r_log.status_code} me={r_me.status_code}"
            t1.fix = "app/api/v1/auth.py, app/main.py lifespan (create users table)"
    except Exception as e:
        t1.error = str(e)
        t1.fix = "Start server: uvicorn app.main:app --port 8080"
    results.append(t1)

    if not t1.passed:
        _print_report(results)
        client.close()
        return 1

    auth_headers = {"Authorization": f"Bearer {token}"}

    # --- TEST 2 Interview Flow ---
    t2 = TestResult("TEST 2 - Interview Flow")
    try:
        if not PDF.is_file():
            raise FileNotFoundError("test_resume.pdf missing")

        r_sess = client.post(
            f"{BASE}/api/v1/interviews/sessions",
            data={
                "role_title": "Backend Developer",
                "experience_level": "mid",
                "topic_focus": "Python",
                "job_description": "Build REST APIs with FastAPI.",
            },
            files={"resume_pdf": ("resume.pdf", PDF.read_bytes(), "application/pdf")},
            headers=auth_headers,
        )
        sid = (r_sess.json() or {}).get("session_id", "")
        r_q = client.post(
            f"{BASE}/api/v1/interviews/sessions/{sid}/questions",
            json={"question_count": 2},
            headers=auth_headers,
        )
        r_cq = client.get(
            f"{BASE}/api/v1/interviews/sessions/{sid}/current-question",
            headers=auth_headers,
        )
        r_ans = client.post(
            f"{BASE}/api/v1/interviews/sessions/{sid}/answers",
            json={
                "answer": (
                    "I design REST APIs with FastAPI, Pydantic validation, "
                    "async SQLAlchemy, and structured error handling."
                )
            },
            headers=auth_headers,
        )
        # second question if more
        cq2 = client.get(
            f"{BASE}/api/v1/interviews/sessions/{sid}/current-question",
            headers=auth_headers,
        )
        if cq2.status_code == 200 and (cq2.json() or {}).get("question"):
            client.post(
                f"{BASE}/api/v1/interviews/sessions/{sid}/answers",
                json={
                    "answer": (
                        "For testing I use pytest, TestClient, and mocks for "
                        "external services to keep tests fast and reliable."
                    )
                },
                headers=auth_headers,
            )
        r_end = client.post(
            f"{BASE}/api/v1/interviews/sessions/{sid}/end",
            headers=auth_headers,
        )
        end_body = r_end.json() if r_end.status_code == 200 else {}
        final_score = end_body.get("final_score") or end_body.get("adjusted_final_score")
        t2.response = jdump(
            {
                "session": r_sess.status_code,
                "questions": r_q.status_code,
                "current_question": r_cq.status_code,
                "answer": r_ans.status_code,
                "end": r_end.status_code,
                "final_score": final_score,
                "end_snippet": end_body,
            }
        )
        t2.passed = all(
            x == 200 or x == 201
            for x in (r_sess.status_code, r_q.status_code, r_cq.status_code, r_ans.status_code, r_end.status_code)
        ) and final_score is not None
        if not t2.passed:
            t2.error = f"sess={r_sess.status_code} q={r_q.status_code} end={r_end.status_code} score={final_score}"
            t2.fix = "app/services/interview_service.py, app/routes/interview_routes.py, LLM keys in .env"
    except Exception as e:
        t2.error = str(e)
        t2.fix = "interview_service.py / question_generator / GROQ_API_KEY"
    results.append(t2)

    # --- TEST 3 Judge/Scoring ---
    t3 = TestResult("TEST 3 - Judge/Scoring")
    try:
        judgments = end_body.get("answer_judgments") or []
        if not judgments and t2.passed:
            r_end2 = client.post(
                f"{BASE}/api/v1/interviews/sessions/{sid}/end",
                headers=auth_headers,
            )
            judgments = (r_end2.json() or {}).get("answer_judgments") or []
        ok_fields = False
        sample = None
        for j in judgments:
            if not j:
                continue
            sample = j
            ok_fields = all(
                k in j
                for k in ("criteria_scores", "weighted_total", "strengths", "improvements")
            ) and isinstance(j.get("weighted_total"), (int, float))
            if ok_fields:
                break
        t3.response = jdump({"judgments_count": len(judgments), "sample": sample})
        t3.passed = ok_fields
        if not t3.passed:
            t3.error = "Missing criteria_scores/weighted_total/strengths/improvements in answer_judgments"
            t3.fix = "app/judge/judge.py — ensure JSON schema; interview_service.submit_answer stores full judgment"
    except Exception as e:
        t3.error = str(e)
        t3.fix = "app/judge/judge.py"
    results.append(t3)

    # --- TEST 4 Proctoring ---
    t4 = TestResult("TEST 4 - Proctoring")
    try:
        r_h = client.get(f"{BASE}/proctor/health")
        r_r = client.post(f"{BASE}/proctor/reset", json={"session_id": sid or None})
        t4.response = jdump(
            {"health": {"status": r_h.status_code, "body": r_h.json()}, "reset": {"status": r_r.status_code, "body": r_r.json()}}
        )
        t4.passed = r_h.status_code == 200 and r_r.status_code == 200
        if not t4.passed:
            t4.error = f"health={r_h.status_code} reset={r_r.status_code}"
            t4.fix = "app/proctoring/api.py, app/main.py proctor mount"
    except Exception as e:
        t4.error = str(e)
        t4.fix = "app/proctoring/api.py"
    results.append(t4)

    # --- TEST 5 Audio Answer (separate session) ---
    t5 = TestResult("TEST 5 - Audio Answer")
    audio_sid = sid
    try:
        if not PDF.is_file():
            raise FileNotFoundError("test_resume.pdf missing")
        r_as = client.post(
            f"{BASE}/api/v1/interviews/sessions",
            data={
                "role_title": "Backend Developer",
                "experience_level": "mid",
                "topic_focus": "Python",
                "job_description": "APIs.",
            },
            files={"resume_pdf": ("resume.pdf", PDF.read_bytes(), "application/pdf")},
            headers=auth_headers,
        )
        audio_sid = (r_as.json() or {}).get("session_id", sid)
        client.post(
            f"{BASE}/api/v1/interviews/sessions/{audio_sid}/questions",
            json={"question_count": 1},
            headers=auth_headers,
        )
        wav = try_speech_wav()
        r_audio = client.post(
            f"{BASE}/api/v1/interviews/sessions/{audio_sid}/audio-answer",
            files={"audio": ("test.wav", wav, "audio/wav")},
            data={"submit": "true"},
            headers=auth_headers,
        )
        body_a = r_audio.json() if r_audio.headers.get("content-type", "").startswith("application/json") else {}
        transcript = (
            body_a.get("transcript")
            or body_a.get("transcription")
            or body_a.get("transcribed_text")
            or ""
        )
        saved = body_a.get("answer_saved") or body_a.get("judgment") is not None or r_audio.status_code == 200
        t5.response = jdump({"status": r_audio.status_code, "body": body_a})
        t5.passed = r_audio.status_code == 200 and bool(transcript) and saved
        if not t5.passed:
            t5.error = f"status={r_audio.status_code} transcript_len={len(str(transcript))} body={jdump(body_a, 400)}"
            t5.fix = "app/services/audio_service.py (OPENAI_API_KEY), interview_routes audio-answer"
    except Exception as e:
        t5.error = str(e)
        t5.fix = "app/services/audio_service.py, OPENAI_API_KEY for Whisper"
    results.append(t5)

    # --- TEST 6 Database ---
    t6 = TestResult("TEST 6 - Database")
    try:
        if not DB_PATH.is_file():
            raise FileNotFoundError(str(DB_PATH))
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT session_id, status, final_score,
                   answer_judgments, proctoring_summary
            FROM sessions ORDER BY updated_at DESC LIMIT 1
            """
        ).fetchone()
        conn.close()
        if row:
            d = dict(row)
            t6.response = jdump(
                {
                    "session_id": d.get("session_id"),
                    "status": d.get("status"),
                    "final_score": d.get("final_score"),
                    "has_judgments": bool(d.get("answer_judgments")),
                    "has_proctoring_summary": bool(d.get("proctoring_summary")),
                }
            )
            t6.passed = (
                d.get("session_id") is not None
                and d.get("status") is not None
                and d.get("final_score") is not None
                and d.get("answer_judgments") not in (None, "", "[]", "null")
            )
        else:
            t6.response = "No rows"
            t6.passed = False
        if not t6.passed:
            t6.error = "Row missing or fields empty"
            t6.fix = "app/services/session_persistence.py — persist on end_interview"
    except Exception as e:
        t6.error = str(e)
        t6.fix = "app/db/session_model.py, session_persistence.py"
    results.append(t6)

    # --- TEST 7 Integrity Report ---
    t7 = TestResult("TEST 7 - Score Penalty System")
    try:
        # seed a violation so report is meaningful
        if sid:
            client.post(
                f"{BASE}/proctor/audio-violation",
                json={"session_id": sid, "message": "Test loud audio"},
            )
        r_ir = client.get(f"{BASE}/proctor/integrity-report", params={"session_id": sid or ""})
        body_ir = r_ir.json() if r_ir.status_code == 200 else {}
        t7.response = jdump(body_ir)
        t7.passed = (
            r_ir.status_code == 200
            and "integrity_level" in body_ir
            and "score_penalty_percent" in body_ir
            and "violations" in body_ir
            and isinstance(body_ir.get("violations"), list)
        )
        if not t7.passed:
            t7.error = f"status={r_ir.status_code} keys={list(body_ir.keys())}"
            t7.fix = "app/proctoring/warning_manager.py get_integrity_report, app/proctoring/api.py"
    except Exception as e:
        t7.error = str(e)
        t7.fix = "app/proctoring/warning_manager.py"
    results.append(t7)

    client.close()
    _print_report(results)
    failed = [r for r in results if not r.passed]
    return 1 if failed else 0


def _print_report(results: list[TestResult]) -> None:
    print("\n" + "=" * 60)
    print("BACKEND VERIFICATION REPORT (port 8080)")
    print("=" * 60)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"\n{r.name}: {status}")
        print(f"  Response: {r.response}")
        if r.error:
            print(f"  Error: {r.error}")
        if r.fix and not r.passed:
            print(f"  Fix: {r.fix}")
    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r.passed)
    print(f"Summary: {passed}/{len(results)} passed")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    sys.exit(main())
