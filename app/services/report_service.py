"""Generate PDF interview reports for recruiters."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from pathlib import Path

from app.models.session import InterviewSession
from app.schemas.recruiter import RecruiterSessionDetail, TranscriptItem
from app.services.question_utils import question_text as extract_question_text


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Heading1"],
            fontSize=18,
            spaceAfter=12,
        ),
        "heading": ParagraphStyle(
            "ReportHeading",
            parent=base["Heading2"],
            fontSize=13,
            spaceBefore=14,
            spaceAfter=6,
            textColor=colors.HexColor("#1e3a5f"),
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["BodyText"],
            fontSize=10,
            leading=14,
            spaceAfter=6,
        ),
        "muted": ParagraphStyle(
            "ReportMuted",
            parent=base["BodyText"],
            fontSize=9,
            leading=12,
            textColor=colors.grey,
        ),
    }


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _format_date(dt: datetime) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    return str(dt)


def _format_violation_time(ts: float | int) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except (TypeError, ValueError, OSError):
        return str(ts)


def _criteria_lines(judgment: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    criteria = judgment.get("criteria_scores") or {}
    for name, data in criteria.items():
        if isinstance(data, dict):
            score = data.get("score")
            reasoning = data.get("reasoning", "")
            if score is not None:
                lines.append(f"  • {name}: {score}/100 — {reasoning}")
    return lines


def _judgment_feedback(item: TranscriptItem) -> list[str]:
    lines: list[str] = []
    j = item.judgment
    if not j or j.get("error"):
        lines.append("Judge feedback: Not available.")
        return lines

    score = j.get("weighted_total")
    if score is not None:
        lines.append(f"Overall question score: {score} / 100")

    lines.extend(_criteria_lines(j))

    reasoning = j.get("overall_reasoning") or j.get("reasoning")
    if reasoning:
        lines.append(f"Summary: {reasoning}")

    strengths = j.get("strengths") or []
    if strengths:
        lines.append("Strengths: " + "; ".join(str(s) for s in strengths))

    improvements = j.get("improvements") or []
    if improvements:
        lines.append("Improvements: " + "; ".join(str(s) for s in improvements))

    return lines


def _violations_timeline(proctoring_summary: Optional[dict[str, Any]]) -> list[str]:
    from app.proctoring.warning_manager import format_violation_type

    if not proctoring_summary:
        return ["No proctoring data recorded for this session."]

    lines = [
        f"Integrity level: {proctoring_summary.get('integrity_level', 'unknown')}",
        f"Total violations: {proctoring_summary.get('total_violations', 0)}",
        f"Score penalty: {proctoring_summary.get('score_penalty_percent', 0)}%",
    ]

    warnings = proctoring_summary.get("violations") or proctoring_summary.get("warnings") or []
    if warnings:
        lines.append("Violations timeline:")
        for w in warnings:
            if isinstance(w, dict):
                vtype = w.get("type", w.get("gaze", "?"))
                vtype_label = format_violation_type(str(vtype))
                severity = w.get("severity", w.get("level", "?"))
                ts = w.get("time", "?")
                time_str = _format_violation_time(ts) if ts != "?" else "?"
                pct = w.get("penalty_percent", "")
                suffix = f" (-{pct}%)" if pct != "" else ""
                reason = w.get("message", w.get("reason", ""))
                lines.append(
                    f"  • [{time_str}] {vtype_label} ({severity}){suffix}: {reason}"
                )
            else:
                lines.append(f"  • {w}")
    else:
        lines.append("No violations recorded.")

    return lines


def generate_session_report_pdf(
    detail: RecruiterSessionDetail,
    proctoring_summary: Optional[dict[str, Any]] = None,
) -> bytes:
    """Build a PDF report and return raw bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="Interview Report",
    )
    styles = _styles()
    story: list = []

    story.append(Paragraph("Interview Report", styles["title"]))
    story.append(Paragraph(f"<b>Candidate:</b> {_escape(detail.candidate_name)}", styles["body"]))
    story.append(Paragraph(f"<b>Role:</b> {_escape(detail.role_title)}", styles["body"]))
    story.append(
        Paragraph(
            f"<b>Date:</b> {_escape(_format_date(detail.date))}",
            styles["body"],
        )
    )
    if detail.duration_minutes is not None:
        story.append(
            Paragraph(
                f"<b>Duration:</b> {detail.duration_minutes} minute(s)",
                styles["body"],
            )
        )
    story.append(
        Paragraph(
            f"<b>Status:</b> {_escape(detail.status)} · "
            f"{detail.answered_count}/{detail.total_questions} questions answered",
            styles["body"],
        )
    )

    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("Overall score", styles["heading"]))

    if detail.original_score is not None:
        story.append(
            Paragraph(
                f"Original score: <b>{detail.original_score}</b> / 100",
                styles["body"],
            )
        )
    if detail.integrity_penalty_percent > 0:
        story.append(
            Paragraph(
                f"Integrity penalty: <b>-{detail.integrity_penalty_percent}%</b>",
                styles["body"],
            )
        )
    if detail.adjusted_score is not None:
        rec = (detail.final_score or {}).get("recommendation")
        rec_text = f" — Recommendation: {rec}" if rec else ""
        story.append(
            Paragraph(
                f"Adjusted score: <b>{detail.adjusted_score}</b> / 100{rec_text}",
                styles["body"],
            )
        )
    elif detail.final_score:
        overall = detail.final_score.get("final_score", detail.final_score.get("candidate_score"))
        if overall is not None:
            rec = detail.final_score.get("recommendation")
            rec_text = f" — Recommendation: {rec}" if rec else ""
            story.append(
                Paragraph(f"<b>{overall}</b> / 100{rec_text}", styles["body"])
            )
    else:
        story.append(Paragraph("No overall score available.", styles["muted"]))

    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("Proctoring & integrity", styles["heading"]))
    summary = proctoring_summary or detail.proctoring_summary
    for line in _violations_timeline(summary):
        story.append(Paragraph(_escape(line), styles["body"]))

    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("Session recording", styles["heading"]))
    if detail.recording_available:
        path_hint = detail.recording_filename or "uploads/"
        story.append(
            Paragraph(
                f"Recording available: <b>Yes</b><br/>File: {_escape(path_hint)}",
                styles["body"],
            )
        )
    else:
        story.append(Paragraph("Recording available: <b>No</b>", styles["body"]))

    for item in detail.transcript:
        story.append(Spacer(1, 0.12 * inch))
        story.append(Paragraph(f"Question {item.index}", styles["heading"]))
        story.append(Paragraph(_escape(item.question), styles["body"]))
        story.append(Paragraph("<b>Answer</b>", styles["body"]))
        answer = item.answer if item.answer else "(not answered)"
        story.append(Paragraph(_escape(answer), styles["body"]))
        story.append(Paragraph("<b>Judge feedback</b>", styles["body"]))
        for line in _judgment_feedback(item):
            story.append(Paragraph(_escape(line), styles["body"]))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def report_filename(detail: RecruiterSessionDetail) -> str:
    safe_name = "".join(
        c if c.isalnum() or c in "-_" else "-" for c in detail.candidate_name
    ).strip("-") or "candidate"
    session_short = str(detail.session_id).replace("-", "")[:8]
    return f"interview-report-{safe_name}-{session_short}.pdf"


def _candidate_display_name(session: InterviewSession) -> str:
    if session.candidate_name and session.candidate_name != "Unknown Candidate":
        return session.candidate_name
    resume_filename = session.resume_filename
    if not resume_filename or not resume_filename.strip():
        return "Candidate"
    stem = Path(resume_filename).stem
    if not stem:
        return "Candidate"
    return stem.replace("_", " ").replace("-", " ").strip().title()


def _format_integrity_level(level: str | None) -> str:
    if not level:
        return "Clean"
    return " ".join(word.capitalize() for word in level.split("_"))


def _candidate_judgment_lines(judgment: dict[str, Any] | None) -> list[str]:
    if not judgment or judgment.get("error"):
        return ["Feedback for this answer is not available yet."]

    lines: list[str] = []
    strengths = judgment.get("strengths") or []
    if strengths:
        lines.append("Strengths:")
        for item in strengths:
            lines.append(f"  • {item}")

    improvements = judgment.get("improvements") or []
    if improvements:
        lines.append("Areas to improve:")
        for item in improvements:
            lines.append(f"  • {item}")

    if not lines:
        lines.append("Keep practicing — every interview helps you improve.")
    return lines


def _performance_level(score: float | None) -> str:
    if score is None:
        return "Not available"
    if score >= 85:
        return "Excellent Performance"
    if score >= 70:
        return "Good Performance"
    if score >= 50:
        return "Average Performance"
    return "Needs Improvement"


def _integrity_status_label(session: InterviewSession) -> str:
    proctoring = session.proctoring_summary if isinstance(session.proctoring_summary, dict) else {}
    violations = int(proctoring.get("total_violations", 0) or 0)
    level = str(proctoring.get("integrity_level") or "").lower()
    if violations > 0 or level in {"flagged", "suspicious", "high_risk"}:
        return "Flagged"
    return "Clean"


def _question_scores(session: InterviewSession) -> list[float]:
    scores: list[float] = []
    for judgment_raw in session.answer_judgments:
        if not isinstance(judgment_raw, dict) or judgment_raw.get("error"):
            continue
        raw = judgment_raw.get("weighted_total")
        if isinstance(raw, (int, float)):
            scores.append(float(raw))
    return scores


def _aggregate_feedback(session: InterviewSession) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    improvements: list[str] = []
    for judgment_raw in session.answer_judgments:
        if not isinstance(judgment_raw, dict):
            continue
        for item in judgment_raw.get("strengths") or []:
            text = str(item).strip()
            if text and text not in strengths:
                strengths.append(text)
        for item in judgment_raw.get("improvements") or []:
            text = str(item).strip()
            if text and text not in improvements:
                improvements.append(text)
    return strengths[:3], improvements[:3]


def generate_candidate_report_pdf(
    session: InterviewSession,
    *,
    candidate_name: str | None = None,
    duration_minutes: int | None = None,
    interview_date: datetime | None = None,
) -> bytes:
    """Build a three-page candidate-facing PDF (no hire/no-hire or violation details)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="My Interview Report",
    )
    styles = _styles()
    story: list = []

    name = candidate_name or _candidate_display_name(session)
    report_date = interview_date or session.created_at
    final = session.final_score or {}
    display_score = final.get("original_score")
    if display_score is None:
        display_score = final.get("final_score", final.get("candidate_score"))
    if isinstance(display_score, (int, float)):
        display_score = float(display_score)
    else:
        q_scores = _question_scores(session)
        display_score = round(sum(q_scores) / len(q_scores), 1) if q_scores else None

    # ── Page 1: Summary ─────────────────────────────────────
    story.append(Paragraph("AI Interview Bot", styles["title"]))
    story.append(Paragraph("Your Personal Interview Report", styles["heading"]))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(f"<b>Candidate Name:</b> {_escape(name)}", styles["body"]))
    story.append(
        Paragraph(f"<b>Role Applied For:</b> {_escape(session.role_title)}", styles["body"])
    )
    story.append(
        Paragraph(
            f"<b>Interview Date:</b> {_escape(_format_date(report_date))}",
            styles["body"],
        )
    )
    if duration_minutes is not None:
        story.append(
            Paragraph(
                f"<b>Duration:</b> {duration_minutes} minute(s)",
                styles["body"],
            )
        )
    story.append(Spacer(1, 0.15 * inch))
    if display_score is not None:
        story.append(
            Paragraph(
                f"<b>Overall Score:</b> {display_score} / 100",
                styles["body"],
            )
        )
        story.append(
            Paragraph(
                f"<b>Performance Level:</b> {_escape(_performance_level(display_score))}",
                styles["body"],
            )
        )
    else:
        story.append(Paragraph("<b>Overall Score:</b> Not available", styles["muted"]))
    story.append(
        Paragraph(
            f"<b>Integrity Status:</b> {_integrity_status_label(session)}",
            styles["body"],
        )
    )

    # ── Page 2: Detailed feedback ───────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Detailed Feedback", styles["title"]))

    for i, question in enumerate(session.questions):
        answer = session.answers[i] if i < len(session.answers) else ""
        judgment_raw = (
            session.answer_judgments[i] if i < len(session.answer_judgments) else None
        )
        judgment = judgment_raw if isinstance(judgment_raw, dict) else None

        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(f"Question {i + 1}", styles["heading"]))
        story.append(Paragraph(_escape(extract_question_text(question)), styles["body"]))
        story.append(Paragraph("<b>Your Answer</b>", styles["body"]))
        story.append(
            Paragraph(_escape(answer if answer else "(not answered)"), styles["body"])
        )
        q_score = None
        if judgment and not judgment.get("error"):
            raw = judgment.get("weighted_total")
            if isinstance(raw, (int, float)):
                q_score = float(raw)
        if q_score is not None:
            story.append(
                Paragraph(f"<b>Score for this answer:</b> {q_score} / 100", styles["body"])
            )
        story.append(Paragraph("<b>What you did well:</b>", styles["body"]))
        strengths = (judgment or {}).get("strengths") or []
        if strengths:
            for item in strengths:
                story.append(Paragraph(f"• {_escape(str(item))}", styles["body"]))
        else:
            story.append(Paragraph("• Keep building on your interview practice.", styles["muted"]))
        story.append(Paragraph("<b>Areas to improve:</b>", styles["body"]))
        improvements = (judgment or {}).get("improvements") or []
        if improvements:
            for item in improvements:
                story.append(Paragraph(f"• {_escape(str(item))}", styles["body"]))
        else:
            story.append(Paragraph("• Continue refining your technical explanations.", styles["muted"]))
        story.append(Spacer(1, 0.12 * inch))

    # ── Page 3: Summary note ────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Summary Note", styles["title"]))
    story.append(
        Paragraph("Thank you for completing this interview.", styles["body"])
    )
    answered = len(session.answers)
    story.append(
        Paragraph(f"<b>Total questions answered:</b> {answered}", styles["body"])
    )
    q_scores = _question_scores(session)
    if q_scores:
        avg = round(sum(q_scores) / len(q_scores), 1)
        story.append(
            Paragraph(f"<b>Average score across all questions:</b> {avg} / 100", styles["body"])
        )
    top_strengths, top_improvements = _aggregate_feedback(session)
    if top_strengths:
        story.append(Paragraph("<b>Top strengths overall:</b>", styles["body"]))
        for item in top_strengths:
            story.append(Paragraph(f"• {_escape(item)}", styles["body"]))
    if top_improvements:
        story.append(Paragraph("<b>Top areas for improvement overall:</b>", styles["body"]))
        for item in top_improvements:
            story.append(Paragraph(f"• {_escape(item)}", styles["body"]))
    story.append(Spacer(1, 0.15 * inch))
    story.append(
        Paragraph(
            _escape(
                "Keep practicing and improving. Best of luck with your career journey."
            ),
            styles["body"],
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def candidate_report_filename(
    session: InterviewSession,
    *,
    candidate_name: str | None = None,
) -> str:
    display = candidate_name or _candidate_display_name(session)
    safe_name = "".join(
        c if c.isalnum() or c in "-_" else "-" for c in display
    ).strip("-") or "candidate"
    session_short = str(session.session_id).replace("-", "")[:8]
    return f"my-interview-report-{safe_name}-{session_short}.pdf"
