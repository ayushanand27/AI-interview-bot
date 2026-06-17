"""Quick verification: recruiter dashboard, recording, PDF report."""
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
UPLOADS = ROOT / "uploads"
DB = ROOT / "smartskale.db"
OUT = ROOT / "scripts" / "verify_report.json"


def http(method, path, *, data=None, token=None, multipart=None, raw_body=False):
    url = BASE + path
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if multipart:
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
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if raw_body or "application/pdf" in ct or "video/" in ct:
                return resp.status, raw, ct
            if "application/json" in ct:
                return resp.status, json.loads(raw.decode()), ct
            return resp.status, raw.decode(errors="replace"), ct
    except urllib.error.HTTPError as e:
        raw = e.read()
        ct = e.headers.get("Content-Type", "")
        try:
            return e.code, json.loads(raw.decode()), ct
        except json.JSONDecodeError:
            return e.code, raw, ct


def login_or_register_recruiter():
    ts = int(time.time())
    email = f"verify_recruiter_{ts}@example.com"
    password = "VerifyPass123!"
    code, body, _ = http(
        "POST",
        "/api/v1/auth/register",
        data={
            "full_name": "Verify Recruiter",
            "email": email,
            "password": password,
            "role": "recruiter",
        },
    )
    if code == 201:
        return body["data"]["access_token"]
    code, body, _ = http(
        "POST",
        "/api/v1/auth/login",
        data={"email": email, "password": password},
    )
    return body["data"]["access_token"] if code == 200 else None


def login_candidate():
    ts = int(time.time())
    email = f"verify_candidate_{ts}@example.com"
    password = "VerifyPass123!"
    http(
        "POST",
        "/api/v1/auth/register",
        data={
            "full_name": "Verify Candidate",
            "email": email,
            "password": password,
            "role": "candidate",
        },
    )
    code, body, _ = http(
        "POST",
        "/api/v1/auth/login",
        data={"email": email, "password": password},
    )
    return body["data"]["access_token"] if code == 200 else None


def make_minimal_webm() -> bytes:
    # Not a valid webm but enough for upload path test
    return b"\x1a\x45\xdf\xa3" + b"\x00" * 128


def extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        import pypdf
        from io import BytesIO as BIO

        reader = pypdf.PdfReader(BIO(pdf_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        # Fallback: crude ASCII extraction
        return pdf_bytes.decode("latin-1", errors="ignore")


def main():
    report = {"features": []}

    # --- Feature 1: Recruiter ---
    f1 = {"name": "RECRUITER DASHBOARD", "pass": False, "details": {}}
    recruiter_token = login_or_register_recruiter()
    if not recruiter_token:
        f1["details"]["error"] = "Could not obtain recruiter token"
        report["features"].append(f1)
    else:
        code, body, _ = http("GET", "/api/v1/recruiter/sessions", token=recruiter_token)
        f1["details"]["list_status"] = code
        sessions = body.get("data", []) if isinstance(body, dict) else []
        f1["details"]["session_count"] = len(sessions)
        f1["details"]["sample_sessions"] = sessions[:3] if sessions else []

        session_id = sessions[0]["session_id"] if sessions else None
        if not session_id and DB.exists():
            conn = sqlite3.connect(DB)
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE status IN ('ended','completed') "
                "ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                session_id = str(row[0]).replace("-", "") if len(str(row[0])) == 32 else str(row[0])
                if len(session_id) == 32:
                    session_id = f"{session_id[:8]}-{session_id[8:12]}-{session_id[12:16]}-{session_id[16:20]}-{session_id[20:]}"

        if session_id:
            code2, detail, _ = http(
                f"GET",
                f"/api/v1/recruiter/sessions/{session_id}",
                token=recruiter_token,
            )
            f1["details"]["detail_status"] = code2
            if isinstance(detail, dict) and detail.get("data"):
                d = detail["data"]
                f1["details"]["transcript_items"] = len(d.get("transcript", []))
                f1["details"]["has_final_score"] = d.get("final_score") is not None
                f1["details"]["integrity_level"] = d.get("integrity_level")
                f1["details"]["violations_count"] = len(
                    (d.get("proctoring_summary") or {}).get("violations") or []
                )
                f1["details"]["recording_available"] = d.get("recording_available")
        f1["pass"] = code == 200 and len(sessions) > 0 and f1["details"].get("detail_status") == 200
        report["features"].append(f1)
        report["latest_session_id"] = session_id

    session_id = report.get("latest_session_id")

    # --- Feature 2: Recording ---
    f2 = {"name": "RECORDING", "pass": False, "details": {}}
    f2["details"]["uploads_dir_exists"] = UPLOADS.exists()
    webm_files = list(UPLOADS.glob("*.webm")) if UPLOADS.exists() else []
    f2["details"]["webm_files"] = [str(p.name) for p in webm_files]
    f2["details"]["webm_count"] = len(webm_files)

    candidate_token = login_candidate()
    test_session_id = None
    if candidate_token and RESUME.exists():
        pdf = RESUME.read_bytes()
        code, body, _ = http(
            "POST",
            "/api/v1/interviews/sessions",
            token=candidate_token,
            multipart={
                "fields": {
                    "role_title": "Recording Verify",
                    "experience_level": "mid",
                    "job_description": "Quick recording test.",
                },
                "files": {"resume_pdf": ("test_resume.pdf", pdf, "application/pdf")},
            },
        )
        if code == 201:
            test_session_id = body["session_id"]
            http(
                "POST",
                f"/api/v1/interviews/sessions/{test_session_id}/questions",
                token=candidate_token,
                data={"question_count": 1},
            )
            http(
                "POST",
                f"/api/v1/interviews/sessions/{test_session_id}/answers",
                token=candidate_token,
                data={"answer": "Quick test answer for recording verification."},
            )
            # Upload test recording (simulates frontend upload on end)
            webm = make_minimal_webm()
            code_u, body_u, _ = http(
                "POST",
                f"/api/v1/interviews/sessions/{test_session_id}/recording",
                token=candidate_token,
                multipart={
                    "files": {"video": ("test.webm", webm, "video/webm")},
                },
            )
            f2["details"]["upload_test_status"] = code_u
            f2["details"]["upload_test_body"] = body_u
            http(
                "POST",
                f"/api/v1/interviews/sessions/{test_session_id}/end",
                token=candidate_token,
            )

    webm_files = list(UPLOADS.glob("*.webm")) if UPLOADS.exists() else []
    f2["details"]["webm_files_after"] = [str(p.name) for p in webm_files]

    rec_session = test_session_id or session_id
    if rec_session and recruiter_token:
        code_g, body_g, ct = http(
            "GET",
            f"/api/v1/interviews/sessions/{rec_session}/recording",
            token=recruiter_token,
            raw_body=True,
        )
        f2["details"]["get_recording_status"] = code_g
        f2["details"]["get_recording_content_type"] = ct
        f2["details"]["get_recording_bytes"] = (
            len(body_g) if isinstance(body_g, (bytes, bytearray)) else 0
        )

    f2["pass"] = (
        f2["details"].get("uploads_dir_exists")
        and f2["details"].get("upload_test_status") == 200
        and f2["details"].get("get_recording_status") == 200
        and f2["details"].get("get_recording_bytes", 0) > 0
    )
    report["features"].append(f2)

    # --- Feature 3: PDF Report ---
    f3 = {"name": "PDF REPORT", "pass": False, "details": {}}
    pdf_session = rec_session or session_id
    if recruiter_token and pdf_session:
        code, body, ct = http(
            "GET",
            f"/api/v1/recruiter/sessions/{pdf_session}/report",
            token=recruiter_token,
            raw_body=True,
        )
        f3["details"]["status"] = code
        f3["details"]["content_type"] = ct
        if isinstance(body, bytes):
            pdf_path = ROOT / "scripts" / "verify_report_sample.pdf"
            pdf_path.write_bytes(body)
            f3["details"]["pdf_path"] = str(pdf_path)
            f3["details"]["pdf_bytes"] = len(body)
            f3["details"]["is_pdf_magic"] = body[:4] == b"%PDF"
            text = extract_pdf_text(body)
            f3["details"]["pdf_text_preview"] = text[:2000]
            checks = {
                "candidate_info": "Candidate:" in text or "Interview Report" in text,
                "scores": "score" in text.lower() or "Score" in text,
                "violations": "violation" in text.lower() or "Proctoring" in text,
                "recording_info": "Recording" in text,
            }
            f3["details"]["field_checks"] = checks
            f3["pass"] = code == 200 and f3["details"]["is_pdf_magic"] and all(checks.values())
        else:
            f3["details"]["error_body"] = str(body)[:500]
    report["features"].append(f3)

    # verify-environment smoke test
    code, body, _ = http(
        "POST",
        "/proctor/verify-environment",
        data={
            "session_id": str(uuid.uuid4()),
            "user_agent": "verify-script",
            "detected_extensions": [],
            "virtual_camera_detected": False,
            "screen_sharing_active": False,
        },
    )
    report["verify_environment"] = {"status": code, "body": body}

    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    for f in report["features"]:
        print(f"{f['name']}: {'PASS' if f['pass'] else 'FAIL'}")
        print(json.dumps(f["details"], indent=2)[:1500])
        print("---")
    print("verify-environment:", report["verify_environment"])
    print("Full report:", OUT)
    return 0 if all(f["pass"] for f in report["features"]) else 1


if __name__ == "__main__":
    sys.exit(main())
