from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services import recruiter_service
from app.services.report_service import generate_session_report_pdf


def _session_row():
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        session_id=uuid4(),
        resume_filename="ayush_sharma_resume.pdf",
        role_title="Backend Engineer",
        experience_level="Mid",
        status="completed",
        updated_at=now,
        created_at=now,
        questions=[{"question": "Explain CAP theorem"}],
        answers=["Consistency, availability, partition tolerance tradeoffs."],
        answer_judgments=[
            {
                "weighted_total": 82,
                "overall_reasoning": "Good fundamentals with concise explanation.",
                "strengths": ["Explained each CAP axis clearly."],
                "improvements": ["Could mention real-world system choices."],
            }
        ],
        total_questions=1,
        final_score={
            "original_score": 84,
            "adjusted_final_score": 76,
            "final_score": 76,
            "recommendation": "Hold",
        },
        proctoring_summary={
            "low_identity_confidence": True,
            "identity_similarity_score": 0.42,
            "identity_liveness_confidence": 0.63,
            "identity_ocr_name_match": False,
        },
        recording_filename="uploads/session-1.webm",
        human_review_flag=True,
    )


def test_session_detail_surfaces_review_and_identity_evidence(monkeypatch):
    row = _session_row()
    monkeypatch.setattr(
        recruiter_service,
        "get_session_review_state",
        lambda _session_id: {
            "human_review_required": True,
            "review_status": "escalated",
            "review_notes": "Identity mismatch needs secondary review.",
            "reviewed_at": datetime(2026, 7, 28, 12, 30, tzinfo=timezone.utc),
            "reviewed_by_user_id": 77,
        },
    )
    monkeypatch.setattr(
        recruiter_service,
        "list_proctor_events",
        lambda _session_id: [
            {
                "type": "tab_switch",
                "severity": "medium",
                "time": 1722169800.0,
                "penalty_percent": 10.0,
                "message": "Candidate switched tabs during preflight.",
                "evidence_metadata": {"phase": "preflight"},
            }
        ],
    )

    attempt = SimpleNamespace(
        verified=False,
        confidence_score=0.64,
        low_identity_confidence=True,
        similarity_score=0.42,
        liveness_mode="multi_frame_sequence",
        liveness_confidence=0.63,
        ocr_name="Ayush Sharma",
        ocr_document_number="XXXX1234",
        ocr_confidence=0.88,
        message="Identity verified with additional review signals.",
        evidence_metadata={
            "warnings": ["The name detected on the ID did not clearly match the candidate details."],
            "ocr_name_match": False,
        },
        created_at=datetime(2026, 7, 28, 12, 1, tzinfo=timezone.utc),
    )

    detail = recruiter_service._session_to_detail(row, attempt)
    summary = recruiter_service._session_to_summary(row)

    assert summary.review_status == "escalated"
    assert summary.integrity_event_count == 1
    assert summary.low_identity_confidence is True

    assert detail.review_state.review_status == "escalated"
    assert detail.review_state.review_notes == "Identity mismatch needs secondary review."
    assert detail.integrity_event_count == 1
    assert detail.proctor_events[0].type == "tab_switch"
    assert detail.identity_verification is not None
    assert detail.identity_verification.low_identity_confidence is True
    assert detail.identity_verification.ocr_name_match is False
    assert detail.identity_verification.warnings


def test_recruiter_report_pdf_includes_phase3_sections(monkeypatch):
    row = _session_row()
    monkeypatch.setattr(recruiter_service, "get_session_review_state", lambda _session_id: None)
    monkeypatch.setattr(recruiter_service, "list_proctor_events", lambda _session_id: [])

    detail = recruiter_service._session_to_detail(row, None)
    pdf = generate_session_report_pdf(detail, detail.proctoring_summary)

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500
