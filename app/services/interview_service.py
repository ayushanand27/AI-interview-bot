"""Core interview flow: Question → Answer → Next Question."""

import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from uuid import UUID

from app.models.schemas import (
    AnswerSubmitResponse,
    CurrentQuestionResponse,
    EndInterviewResponse,
    GenerateQuestionsResponse,
    InterviewSessionResponse,
    SessionStatus,
)
from app.services.llm_service import get_llm_service
from app.models.session import InterviewSession
from app.services.session_store import session_store
from app.core.config import settings
from app.judge.judge import judge_answer
from app.judge.final_score import compute_final_score
from app.models.schemas import AudioAnswerResponse
from app.proctoring.session_registry import (
    get_proctor_integrity_report,
    get_proctor_warning_count,
    get_warning_manager,
)
from app.services.session_persistence import (
    candidate_report_email_already_sent,
    mark_candidate_report_email_sent,
    update_recording_filename,
    update_recording_mp4_filename,
    upsert_session_artifact,
)
from app.services.audio_service import transcribe_audio
from app.core.exceptions import ForbiddenException
from app.utils.exceptions import (
    InvalidSessionStateError,
    QuestionsNotGeneratedError,
    SessionNotFoundError,
)
from app.services.resume_parser import extract_text_from_document
from app.services.object_storage import get_object_storage
from app.utils.file_validation import validate_document_upload
from app.services.question_utils import (
    grade_objective_answer,
    public_question_view,
    question_hidden_tests,
    question_marks,
    question_memory_limit_mb,
    question_public_tests,
    question_text as extract_question_text,
    question_time_limit_ms,
    question_time_seconds,
    question_type,
)
from app.services.coding_judge import (
    LANGUAGE_EXTENSIONS,
    CodingJudgeError,
    coding_judge_configured,
    judgment_from_run_summary,
    public_run_payload,
    run_test_cases,
)
from app.services.adaptive_interview import (
    build_blueprint,
    enrich_seed_questions,
    initial_adaptive_state,
    is_invite_locked,
    maybe_adapt_next_question,
    public_adaptive_flags,
)


logger = logging.getLogger(__name__)


def _candidate_safe_judgments(judgments: list | None) -> list[dict]:
    """Invite candidates: strengths / improvements / short feedback only."""
    safe: list[dict] = []
    for raw in judgments or []:
        if not isinstance(raw, dict):
            safe.append({"error": "unavailable"})
            continue
        if raw.get("error"):
            safe.append({"error": str(raw.get("error"))})
            continue
        item: dict = {}
        if "weighted_total" in raw and raw["weighted_total"] is not None:
            try:
                item["weighted_total"] = float(raw["weighted_total"])
            except (TypeError, ValueError):
                pass
        for key in ("strengths", "improvements"):
            vals = raw.get(key)
            if isinstance(vals, list):
                cleaned = [str(v).strip() for v in vals if str(v).strip()]
                if cleaned:
                    item[key] = cleaned[:5]
        reasoning = raw.get("overall_reasoning") or raw.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            item["overall_reasoning"] = reasoning.strip()[:500]
        safe.append(item)
    return safe


def _candidate_safe_final_score(final: dict | None) -> dict | None:
    """Strip recruiter-only / integrity fields from final_score for invite view."""
    if not isinstance(final, dict):
        return None
    out: dict = {}
    for key in (
        "final_score",
        "candidate_score",
        "recommendation",
        "adjusted_final_score",
    ):
        if key in final and final[key] is not None:
            out[key] = final[key]
    for key in ("top_strengths", "top_improvements"):
        vals = final.get(key)
        if isinstance(vals, list):
            cleaned = [str(v).strip() for v in vals if str(v).strip()]
            if cleaned:
                out[key] = cleaned[:4]
    return out or None


def resolve_job_description(
    job_description: str | None,
    job_description_pdf_bytes: bytes | None,
    *,
    pdf_filename: str | None = None,
    pdf_content_type: str | None = None,
    upload_filename: str | None = None,
    upload_content_type: str | None = None,
) -> str:
    """Combine pasted JD text with text extracted from an uploaded document."""
    filename = upload_filename or pdf_filename
    content_type = (
        upload_content_type if upload_content_type is not None else pdf_content_type
    )

    parts: list[str] = []
    if job_description and job_description.strip():
        parts.append(job_description.strip())

    if job_description_pdf_bytes:
        file_name = filename or "job-description.pdf"
        validate_document_upload(
            job_description_pdf_bytes,
            content_type,
            file_name,
        )
        parts.append(
            extract_text_from_document(job_description_pdf_bytes, file_name)
        )

    combined = "\n\n".join(part for part in parts if part.strip())
    if not combined.strip():
        raise ValueError(
            "Job description is required. Paste text or upload a PDF, Word, or TXT file."
        )
    return combined.strip()


class InterviewService:
    """Orchestrates session lifecycle and one-question-at-a-time flow."""

    def _get_session_or_404(self, session_id: UUID) -> InterviewSession:
        session = session_store.get(session_id)
        if session is None:
            raise SessionNotFoundError(str(session_id))
        return session

    def _ensure_session_owner(self, session: InterviewSession, user_id: int) -> None:
        if session.user_id is None:
            raise ForbiddenException(
                "This interview session is not linked to an account."
            )
        if session.user_id != user_id:
            raise ForbiddenException(
                "You do not have access to this interview session."
            )

    def _get_session_for_user(self, session_id: UUID, user_id: int) -> InterviewSession:
        session = self._get_session_or_404(session_id)
        self._ensure_session_owner(session, user_id)
        return session

    def verify_session_access(self, session_id: UUID, user_id: int) -> None:
        """Ensure the authenticated user owns this session (e.g. transcribe-only audio)."""
        self._get_session_for_user(session_id, user_id)

    def _build_judged_items(self, session: InterviewSession) -> list[dict]:
        judged_items: list[dict] = []
        for i, q in enumerate(session.questions):
            a = session.answers[i] if i < len(session.answers) else ""
            j = session.answer_judgments[i] if i < len(session.answer_judgments) else None
            if j is not None:
                judged_items.append(
                    {
                        "index": i + 1,
                        "question": extract_question_text(q),
                        "answer": a,
                        "judgment": j,
                        "marks": question_marks(q),
                    }
                )
        return judged_items

    def _extract_original_score(self, final_score: dict | None) -> float | None:
        if not final_score:
            return None
        raw = final_score.get("original_score")
        if raw is None:
            raw = final_score.get("final_score")
        if raw is None:
            raw = final_score.get("candidate_score")
        if isinstance(raw, (int, float)):
            return float(raw)
        return None

    def _compute_and_save_final_score(self, session: InterviewSession) -> dict | None:
        """Aggregate per-question judgments into session.final_score and persist."""
        judged_items = self._build_judged_items(session)
        if not judged_items:
            return None
        final = compute_final_score(judged_items)
        session.final_score = final
        return final

    def reset_active_sessions(self, user_id: int) -> dict[str, str]:
        """Manually abandon in-flight sessions so the candidate can start fresh."""
        return {
            "message": "Active session cleared. You can start a new interview."
        }

    def create_session(
        self,
        *,
        user_id: int,
        role_title: str,
        experience_level: str,
        topic_focus: str | None,
        resume_filename: str | None,
        resume_text: str | None,
        job_description: str | None,
    ) -> InterviewSessionResponse:
        session = session_store.create(
            user_id=user_id,
            role_title=role_title,
            experience_level=experience_level,
            topic_focus=topic_focus,
            resume_filename=resume_filename,
            resume_text=resume_text,
            job_description=job_description,
        )
        return self._to_session_response(session)

    def generate_questions(
        self,
        session_id: UUID,
        user_id: int,
        question_count: int | None = None,
    ) -> GenerateQuestionsResponse:
        session = self._get_session_for_user(session_id, user_id)

        if session.status not in (SessionStatus.CREATED, SessionStatus.QUESTIONS_READY):
            raise InvalidSessionStateError(
                "Cannot generate questions unless session is in 'created' state."
            )

        count = question_count or settings.INTERVIEW_QUESTION_COUNT

        questions = get_llm_service().generate_interview_questions(
            role_title=session.role_title,
            experience_level=session.experience_level,
            question_count=count,
            topic_focus=session.topic_focus,
            resume_text=session.resume_text,
            job_description=session.job_description,
        )

        # Invite assessments stay on fixed banks; open interviews get adaptive state.
        if is_invite_locked(session):
            session.questions = questions
            session.adaptive_state = None
        else:
            blueprint = build_blueprint(
                role_title=session.role_title,
                experience_level=session.experience_level,
                question_count=count,
                topic_focus=session.topic_focus,
                job_description=session.job_description,
                resume_text=session.resume_text,
            )
            session.questions = enrich_seed_questions(questions, blueprint)
            session.adaptive_state = initial_adaptive_state(blueprint)

        session.answers = []
        session.current_question_index = 0
        session.status = SessionStatus.QUESTIONS_READY
        session_store.save(session)

        return GenerateQuestionsResponse(
            session_id=session.session_id,
            status=session.status,
            total_questions=session.total_questions,
            message="Questions generated. Fetch the current question to begin.",
        )

    def get_current_question(
        self, session_id: UUID, user_id: int
    ) -> CurrentQuestionResponse:
        session = self._get_session_for_user(session_id, user_id)

        if not session.questions:
            raise QuestionsNotGeneratedError()

        proctor_warnings = get_proctor_warning_count(session.session_id)
        if proctor_warnings == 0 and session.proctoring_summary:
            proctor_warnings = int(
                session.proctoring_summary.get(
                    "total_violations",
                    session.proctoring_summary.get("warning_count", 0),
                )
            )

        if session.is_complete or session.status in (
            SessionStatus.COMPLETED,
            SessionStatus.ENDED,
        ):
            return CurrentQuestionResponse(
                session_id=session.session_id,
                status=session.status,
                question_index=session.current_question_index,
                total_questions=session.total_questions,
                question=None,
                is_complete=True,
                message="Interview is complete. No more questions.",
                proctor_warning_count=proctor_warnings,
            )

        # First access moves session into active interview
        if session.status == SessionStatus.QUESTIONS_READY:
            session.status = SessionStatus.IN_PROGRESS
            session_store.save(session)
            invite_token = getattr(session, "invite_token", None)
            if invite_token:
                from app.services.invite_funnel import record_invite_funnel_event

                record_invite_funnel_event(
                    invite_token=str(invite_token),
                    event_type="started",
                    session_id=session.session_id,
                )

        index = session.current_question_index
        raw_question = session.questions[index]
        view = public_question_view(
            raw_question,
            shuffle_seed=f"{session.session_id}:{index}",
        )
        adaptive_flags = public_adaptive_flags(raw_question)

        return CurrentQuestionResponse(
            session_id=session.session_id,
            status=session.status,
            question_index=index,
            total_questions=session.total_questions,
            question=view["text"],
            is_complete=False,
            message="Answer this question, then submit your response.",
            proctor_warning_count=proctor_warnings,
            time_seconds=int(view.get("time_seconds") or question_time_seconds(raw_question)),
            marks=float(view.get("marks") or question_marks(raw_question)),
            question_type=str(view.get("type") or question_type(raw_question)),
            options=view.get("options"),
            tolerance=view.get("tolerance"),
            languages=view.get("languages"),
            starter_code=view.get("starter_code"),
            public_tests=view.get("public_tests"),
            time_limit_ms=view.get("time_limit_ms"),
            memory_limit_mb=view.get("memory_limit_mb"),
            is_adaptive_follow_up=bool(adaptive_flags.get("is_adaptive_follow_up")),
            adaptive_topic=adaptive_flags.get("adaptive_topic"),
            adaptive_difficulty=adaptive_flags.get("adaptive_difficulty"),
        )

    def submit_answer(
        self, session_id: UUID, answer: str, user_id: int
    ) -> AnswerSubmitResponse:
        session = self._get_session_for_user(session_id, user_id)

        if not session.questions:
            raise QuestionsNotGeneratedError()

        if get_warning_manager(str(session_id)).terminated:
            raise InvalidSessionStateError(
                "Interview locked due to integrity violations. Contact the recruiter."
            )

        if session.status not in (
            SessionStatus.IN_PROGRESS,
            SessionStatus.QUESTIONS_READY,
        ):
            raise InvalidSessionStateError(
                f"Cannot submit answers when session status is '{session.status.value}'."
            )

        if session.is_complete:
            raise InvalidSessionStateError("Interview is already complete.")

        index = session.current_question_index
        if index >= session.total_questions:
            raise InvalidSessionStateError("No active question to answer.")

        # Store answer aligned with current question index
        if len(session.answers) <= index:
            session.answers.append(answer.strip())
        else:
            session.answers[index] = answer.strip()

        # Ensure answer_judgments list aligns with answers list
        if len(session.answer_judgments) <= index:
            session.answer_judgments.append(None)

        session.current_question_index += 1

        has_more = session.current_question_index < session.total_questions
        if not has_more:
            session.status = SessionStatus.COMPLETED

        session_store.save(session)

        # Objective types graded server-side; coding uses Judge0; subjective uses LLM judge
        raw_question = session.questions[index]
        try:
            qtype = question_type(raw_question)
            if qtype == "coding":
                # Legacy path: treat as unanswered coding if posted via /answers
                judgment = {
                    "weighted_total": 0.0,
                    "overall_reasoning": (
                        "Coding answers must be submitted via the coding endpoint."
                    ),
                    "grading_mode": "coding_judge",
                    "error": "use_coding_endpoint",
                }
            else:
                objective = grade_objective_answer(raw_question, answer.strip())
                if objective is not None:
                    judgment = objective
                else:
                    question_prompt = extract_question_text(raw_question)
                    judgment = judge_answer(
                        question=question_prompt,
                        answer=answer.strip(),
                        job_role=session.role_title,
                    )
        except Exception:
            judgment = {"error": "judging_failed"}

        # store judgment parallel to answers
        session.answer_judgments[index] = judgment

        # Phase 5: adapt the next remaining subjective question when enabled.
        if has_more:
            maybe_adapt_next_question(
                session,
                answered_index=index,
                judgment=judgment if isinstance(judgment, dict) else None,
                generate_follow_up=get_llm_service().generate_follow_up_question,
            )

        if session.current_question_index >= session.total_questions:
            self._compute_and_save_final_score(session)

        session_store.save(session)

        remaining = max(session.total_questions - session.current_question_index, 0)
        if has_more:
            message = (
                f"Answer saved for question {index + 1} of {session.total_questions}. "
                f"Call GET /current-question next ({remaining} question(s) remaining)."
            )
        else:
            message = "Final answer saved. Interview complete."

        return AnswerSubmitResponse(
            session_id=session.session_id,
            status=session.status,
            answered_question_index=index,
            message=message,
            has_more_questions=has_more,
            is_complete=not has_more,
            remaining_questions=remaining,
        )

    def run_coding_public_tests(
        self,
        session_id: UUID,
        user_id: int,
        *,
        language: str,
        source: str,
    ) -> dict:
        """Run candidate code against public tests only (does not advance session)."""
        session = self._get_session_for_user(session_id, user_id)
        if not session.questions:
            raise QuestionsNotGeneratedError()
        if session.status not in (
            SessionStatus.IN_PROGRESS,
            SessionStatus.QUESTIONS_READY,
        ):
            raise InvalidSessionStateError(
                f"Cannot run code when session status is '{session.status.value}'."
            )
        index = session.current_question_index
        if index >= session.total_questions:
            raise InvalidSessionStateError("No active question to run.")
        raw_question = session.questions[index]
        if question_type(raw_question) != "coding":
            raise InvalidSessionStateError("Current question is not a coding question.")
        if not coding_judge_configured():
            raise InvalidSessionStateError(
                "Coding judge is not configured. Set JUDGE0_RAPIDAPI_KEY."
            )

        if session.status == SessionStatus.QUESTIONS_READY:
            session.status = SessionStatus.IN_PROGRESS
            session_store.save(session)

        tests = question_public_tests(raw_question)
        try:
            summary = run_test_cases(
                source=source,
                language=language,
                tests=tests,
                time_limit_ms=question_time_limit_ms(raw_question),
                memory_limit_mb=question_memory_limit_mb(raw_question),
            )
        except CodingJudgeError as exc:
            return {
                "session_id": session.session_id,
                "question_index": index,
                "passed": 0,
                "total": len(tests),
                "error": str(exc),
                "cases": [],
            }

        payload = public_run_payload(summary)
        return {
            "session_id": session.session_id,
            "question_index": index,
            **payload,
        }

    def submit_coding_answer(
        self,
        session_id: UUID,
        user_id: int,
        *,
        language: str,
        source: str,
    ) -> AnswerSubmitResponse:
        """Store coding source, grade against hidden tests via Judge0, advance index."""
        session = self._get_session_for_user(session_id, user_id)

        if not session.questions:
            raise QuestionsNotGeneratedError()

        if get_warning_manager(str(session_id)).terminated:
            raise InvalidSessionStateError(
                "Interview locked due to integrity violations. Contact the recruiter."
            )

        if session.status not in (
            SessionStatus.IN_PROGRESS,
            SessionStatus.QUESTIONS_READY,
        ):
            raise InvalidSessionStateError(
                f"Cannot submit answers when session status is '{session.status.value}'."
            )

        if session.is_complete:
            raise InvalidSessionStateError("Interview is already complete.")

        index = session.current_question_index
        if index >= session.total_questions:
            raise InvalidSessionStateError("No active question to answer.")

        raw_question = session.questions[index]
        if question_type(raw_question) != "coding":
            raise InvalidSessionStateError(
                "Current question is not a coding question. Use POST /answers."
            )

        ext = LANGUAGE_EXTENSIONS.get(language, "txt")
        storage_key = f"sessions/{session.session_id}/coding/q{index}.{ext}"
        get_object_storage().put_bytes(
            storage_key,
            source.encode("utf-8"),
            content_type="text/plain; charset=utf-8",
        )

        answer_payload = json.dumps(
            {
                "kind": "coding",
                "language": language,
                "s3_key": storage_key,
                "byte_len": len(source.encode("utf-8")),
                "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "preview": source[:500],
            },
            ensure_ascii=False,
        )

        if len(session.answers) <= index:
            session.answers.append(answer_payload)
        else:
            session.answers[index] = answer_payload

        if len(session.answer_judgments) <= index:
            session.answer_judgments.append(None)

        session.current_question_index += 1
        has_more = session.current_question_index < session.total_questions
        if not has_more:
            session.status = SessionStatus.COMPLETED

        session_store.save(session)

        marks = question_marks(raw_question)
        hidden = question_hidden_tests(raw_question)
        # Fall back to public tests if recruiter forgot hidden ones (demo-friendly)
        tests = hidden if hidden else question_public_tests(raw_question)
        try:
            if not coding_judge_configured():
                judgment = {
                    "weighted_total": 0.0,
                    "overall_reasoning": "Coding judge is not configured.",
                    "grading_mode": "coding_judge",
                    "error": "judge_not_configured",
                    "max_marks": float(marks),
                }
            else:
                summary = run_test_cases(
                    source=source,
                    language=language,
                    tests=tests,
                    time_limit_ms=question_time_limit_ms(raw_question),
                    memory_limit_mb=question_memory_limit_mb(raw_question),
                )
                judgment = judgment_from_run_summary(summary, marks=marks)
                if not hidden and tests:
                    judgment["overall_reasoning"] = (
                        (judgment.get("overall_reasoning") or "")
                        + " (graded on public tests — no hidden tests configured)."
                    ).strip()
        except CodingJudgeError as exc:
            judgment = {
                "weighted_total": 0.0,
                "overall_reasoning": str(exc),
                "grading_mode": "coding_judge",
                "error": "judge_unavailable",
                "max_marks": float(marks),
            }
        except Exception:
            logger.exception("Coding judgment failed for session %s", session_id)
            judgment = {"error": "judging_failed", "grading_mode": "coding_judge"}

        session.answer_judgments[index] = judgment

        # Do not adapt coding answers into follow-ups for invite banks (adaptive skips invites).
        if has_more:
            maybe_adapt_next_question(
                session,
                answered_index=index,
                judgment=judgment if isinstance(judgment, dict) else None,
                generate_follow_up=get_llm_service().generate_follow_up_question,
            )

        if session.current_question_index >= session.total_questions:
            self._compute_and_save_final_score(session)

        session_store.save(session)

        remaining = max(session.total_questions - session.current_question_index, 0)
        if has_more:
            message = (
                f"Coding answer saved for question {index + 1} of {session.total_questions}. "
                f"Call GET /current-question next ({remaining} question(s) remaining)."
            )
        else:
            message = "Final coding answer saved. Interview complete."

        return AnswerSubmitResponse(
            session_id=session.session_id,
            status=session.status,
            answered_question_index=index,
            message=message,
            has_more_questions=has_more,
            is_complete=not has_more,
            remaining_questions=remaining,
        )

    def submit_audio_answer(
        self,
        session_id: UUID,
        audio_bytes: bytes,
        user_id: int,
        filename: str = "audio.webm",
    ) -> AudioAnswerResponse:
        """Transcribe audio with Whisper, then run the same flow as submit_answer."""
        self._get_session_for_user(session_id, user_id)
        transcribed = transcribe_audio(audio_bytes, filename=filename)
        result = self.submit_answer(session_id, transcribed, user_id)
        return AudioAnswerResponse(
            transcribed_text=transcribed,
            **result.model_dump(),
        )

    def end_interview(
        self,
        session_id: UUID,
        user_id: int,
        *,
        candidate_email: str,
        candidate_name: str,
    ) -> EndInterviewResponse:
        session = self._get_session_for_user(session_id, user_id)

        if session.status == SessionStatus.CREATED:
            raise InvalidSessionStateError(
                "Cannot end interview before questions are generated."
            )

        session.status = SessionStatus.ENDED
        original_score: float | None = None
        adjusted_final_score: float | None = None
        integrity_penalty_percent = 0.0
        integrity_report: dict | None = None
        integrity_level: str | None = None

        # Use score computed on last answer; only compute if missing (e.g. early end)
        if session.final_score is None:
            try:
                self._compute_and_save_final_score(session)
            except Exception:
                session.final_score = None

        original_score = self._extract_original_score(session.final_score)

        try:
            integrity_report = get_proctor_integrity_report(str(session_id))
            integrity_penalty_percent = float(
                integrity_report.get("score_penalty_percent", 0.0)
            )
            integrity_level = integrity_report.get("integrity_level")
            session.proctoring_summary = get_warning_manager(
                str(session_id)
            ).get_summary()

            if original_score is not None and integrity_penalty_percent > 0:
                adjusted_final_score = round(
                    original_score * (1 - integrity_penalty_percent / 100.0),
                    1,
                )
                if session.final_score is not None:
                    session.final_score = {
                        **session.final_score,
                        "original_score": original_score,
                        "integrity_penalty_percent": integrity_penalty_percent,
                        "adjusted_final_score": adjusted_final_score,
                        "final_score": adjusted_final_score,
                        "candidate_score": adjusted_final_score,
                    }
            elif original_score is not None:
                adjusted_final_score = original_score
        except Exception:
            session.proctoring_summary = None
            if original_score is not None:
                adjusted_final_score = original_score

        session_store.save(session)

        invite_token = getattr(session, "invite_token", None)
        if invite_token:
            from app.services.invite_funnel import record_invite_funnel_event

            record_invite_funnel_event(
                invite_token=str(invite_token),
                event_type="completed",
                session_id=session.session_id,
                candidate_email=candidate_email,
            )

        needs_review = integrity_level in ("moderate_concerns", "serious_concerns")
        proctoring = session.proctoring_summary if isinstance(session.proctoring_summary, dict) else {}
        if proctoring.get("low_identity_confidence"):
            needs_review = True
        if needs_review:
            from app.services.session_persistence import set_human_review_flag

            set_human_review_flag(session.session_id, True)

        answered = len(session.answers)
        unanswered = max(session.total_questions - answered, 0)
        if unanswered > 0:
            message = (
                f"Interview ended early: {answered} of {session.total_questions} "
                f"question(s) answered. {unanswered} question(s) were skipped."
            )
        else:
            message = "Interview session ended. All questions were answered."

        self._maybe_send_completion_report_email(
            session,
            candidate_email=candidate_email,
            candidate_name=candidate_name,
            adjusted_final_score=adjusted_final_score,
            integrity_level=integrity_level,
        )

        report_email_sent = candidate_report_email_already_sent(session.session_id)

        is_invite = bool(getattr(session, "invite_token", None))
        if is_invite:
            # Candidate-safe summary: score + recommendation + short feedback.
            # Show integrity adjustment transparently; hide timeline/recording.
            return EndInterviewResponse(
                session_id=session.session_id,
                status=session.status,
                total_questions=session.total_questions,
                answered_count=answered,
                unanswered_count=unanswered,
                questions=[extract_question_text(q) for q in session.questions],
                answers=[],
                answer_judgments=_candidate_safe_judgments(session.answer_judgments),
                final_score=_candidate_safe_final_score(session.final_score),
                message=message,
                original_score=original_score,
                integrity_penalty_percent=integrity_penalty_percent or 0.0,
                adjusted_final_score=adjusted_final_score,
                integrity_report=None,
                integrity_level=integrity_level,
                candidate_report_email_sent=False,
            )

        return EndInterviewResponse(
            session_id=session.session_id,
            status=session.status,
            total_questions=session.total_questions,
            answered_count=answered,
            unanswered_count=unanswered,
            questions=[extract_question_text(q) for q in session.questions],
            answers=session.answers,
            answer_judgments=session.answer_judgments,
            final_score=session.final_score,
            message=message,
            original_score=original_score,
            integrity_penalty_percent=integrity_penalty_percent or 0.0,
            adjusted_final_score=adjusted_final_score,
            integrity_report=integrity_report,
            integrity_level=integrity_level,
            candidate_report_email_sent=report_email_sent,
        )

    def _to_session_response(self, session: InterviewSession) -> InterviewSessionResponse:
        return InterviewSessionResponse(
            session_id=session.session_id,
            status=session.status,
            role_title=session.role_title,
            experience_level=session.experience_level,
            topic_focus=session.topic_focus,
            total_questions=session.total_questions,
            current_question_index=session.current_question_index,
            created_at=session.created_at,
        )

    def save_session_recording(
        self,
        session_id: UUID,
        video_bytes: bytes,
        user_id: int,
        *,
        ext: str = ".webm",
    ) -> str:
        """Save interview session recording and persist filename on the session row."""
        self._get_session_for_user(session_id, user_id)
        if not video_bytes:
            raise ValueError("Recording file is empty")

        storage = get_object_storage()
        safe_ext = ext if ext in {".webm", ".mp4"} else ".webm"
        filename = f"{session_id}_recording{safe_ext}"
        mime = "video/webm" if safe_ext == ".webm" else "video/mp4"
        storage.put_bytes(filename, video_bytes, content_type=mime)
        path = storage.resolve_local_path(filename)

        if not update_recording_filename(session_id, filename):
            raise SessionNotFoundError(str(session_id))
        upsert_session_artifact(
            artifact_type="session_recording_webm" if safe_ext == ".webm" else "session_recording_mp4",
            session_id=session_id,
            storage_path=filename,
            mime_type=mime,
            file_size_bytes=len(video_bytes),
            metadata_json={
                "source": "candidate_upload",
                "storage_backend": storage.backend,
            },
        )

        if safe_ext == ".webm":
            mp4_path = _convert_recording_to_mp4(str(path))
            if mp4_path:
                mp4_name = Path(mp4_path).name
                mp4_file = Path(mp4_path)
                if mp4_file.is_file():
                    storage.put_bytes(
                        mp4_name,
                        mp4_file.read_bytes(),
                        content_type="video/mp4",
                    )
                update_recording_mp4_filename(session_id, mp4_name)
                upsert_session_artifact(
                    artifact_type="session_recording_mp4",
                    session_id=session_id,
                    storage_path=mp4_name,
                    mime_type="video/mp4",
                    file_size_bytes=mp4_file.stat().st_size if mp4_file.exists() else None,
                    metadata_json={
                        "source": "ffmpeg_transcode",
                        "storage_backend": storage.backend,
                    },
                )

        return filename

    def resolve_recording_file(self, session_id: UUID) -> tuple[Path, str, str]:
        """Return recording path, media type, and download filename (MP4 then WebM)."""
        from app.services.session_persistence import (
            get_recording_filename,
            get_recording_mp4_filename,
        )

        storage = get_object_storage()

        mp4_filename = get_recording_mp4_filename(session_id)
        if mp4_filename:
            try:
                mp4_path = storage.resolve_local_path(mp4_filename)
                return mp4_path, "video/mp4", "interview_recording.mp4"
            except FileNotFoundError:
                pass

        filename = get_recording_filename(session_id)
        if filename:
            try:
                webm_path = storage.resolve_local_path(filename)
                return webm_path, "video/webm", "interview_recording.webm"
            except FileNotFoundError:
                pass

        raise FileNotFoundError(str(session_id))
    def get_session_recording_path(self, session_id: UUID) -> Path:
        """Return path to stored recording file, preferring mp4 when available."""
        path, _, _ = self.resolve_recording_file(session_id)
        return path

    def get_candidate_report(
        self,
        session: InterviewSession,
        *,
        candidate_name: str | None = None,
        duration_minutes: int | None = None,
        interview_date=None,
    ) -> tuple[bytes, str]:
        """Generate a candidate-facing PDF report for an authorized session."""
        from app.services.report_service import (
            candidate_report_filename,
            generate_candidate_report_pdf,
        )

        if session.status not in (SessionStatus.ENDED, SessionStatus.COMPLETED):
            raise InvalidSessionStateError(
                "Report is only available after the interview has ended."
            )

        pdf_bytes = generate_candidate_report_pdf(
            session,
            candidate_name=candidate_name,
            duration_minutes=duration_minutes,
            interview_date=interview_date,
        )
        filename = candidate_report_filename(session, candidate_name=candidate_name)
        upsert_session_artifact(
            artifact_type="candidate_report_pdf",
            session_id=session.session_id,
            storage_path=None,
            mime_type="application/pdf",
            file_size_bytes=len(pdf_bytes),
            metadata_json={"filename": filename, "generated_on_demand": True},
        )
        return pdf_bytes, filename

    def _maybe_send_completion_report_email(
        self,
        session: InterviewSession,
        *,
        candidate_email: str,
        candidate_name: str,
        adjusted_final_score: float | None,
        integrity_level: str | None,
    ) -> None:
        """Send report PDF after completion.

        Invite/exam sessions: email the recruiter (candidate sees score only in UI).
        Open practice sessions: email the candidate as before.
        """
        from app.services.email_service import (
            send_interview_report_email,
            send_recruiter_assessment_report_email,
        )
        from app.services.session_persistence import _get_sync_session_local

        try:
            if candidate_report_email_already_sent(session.session_id):
                logger.info(
                    "[EMAIL] Completion report already sent for session %s",
                    session.session_id,
                )
                return

            pdf_bytes, pdf_filename = self.get_candidate_report(
                session,
                candidate_name=candidate_name,
            )

            invite_token = getattr(session, "invite_token", None)
            if invite_token:
                SessionLocal = _get_sync_session_local()
                with SessionLocal() as db:
                    from sqlalchemy import select as sa_select

                    from app.db.interview_invite_model import InterviewInvite
                    from app.models.user import User

                    invite = db.execute(
                        sa_select(InterviewInvite).where(
                            InterviewInvite.token == str(invite_token)
                        )
                    ).scalar_one_or_none()
                    recruiter = None
                    if invite is not None:
                        recruiter = db.execute(
                            sa_select(User).where(User.id == invite.recruiter_id)
                        ).scalar_one_or_none()
                if recruiter is None or not recruiter.email:
                    logger.warning(
                        "[EMAIL] No recruiter email for invite session %s",
                        session.session_id,
                    )
                    return
                sent = send_recruiter_assessment_report_email(
                    recruiter.email,
                    recruiter.full_name or "Recruiter",
                    candidate_name=candidate_name or "Candidate",
                    role_title=session.role_title,
                    pdf_bytes=pdf_bytes,
                    pdf_filename=pdf_filename,
                    overall_score=adjusted_final_score,
                    integrity_level=integrity_level,
                )
            else:
                sent = send_interview_report_email(
                    candidate_email,
                    candidate_name,
                    role_title=session.role_title,
                    pdf_bytes=pdf_bytes,
                    pdf_filename=pdf_filename,
                    overall_score=adjusted_final_score,
                    integrity_level=integrity_level,
                )
            if sent:
                mark_candidate_report_email_sent(session.session_id)
        except Exception as exc:
            logger.exception(
                "[EMAIL] Failed to send completion report for session %s: %s",
                session.session_id,
                exc,
            )


def _convert_recording_to_mp4(webm_path: str) -> str | None:
    """Convert WebM to MP4 when ffmpeg is available; otherwise keep WebM only."""
    try:
        if not shutil.which("ffmpeg"):
            print("[RECORDING] ffmpeg not found - skipping MP4 conversion")
            print("[RECORDING] Install ffmpeg for MP4 support")
            print("[RECORDING] WebM file is still available for playback")
            return None

        mp4_path = webm_path.replace(".webm", ".mp4")

        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                webm_path,
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                "-y",
                mp4_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0 and os.path.exists(mp4_path):
            print(f"[RECORDING] MP4 conversion successful: {mp4_path}")
            return mp4_path

        print(f"[RECORDING] FFmpeg conversion failed: {result.stderr[:200]}")
        return None

    except subprocess.TimeoutExpired:
        print("[RECORDING] FFmpeg timed out")
        return None
    except Exception as exc:
        print(f"[RECORDING] Conversion error: {exc}")
        return None


interview_service = InterviewService()
