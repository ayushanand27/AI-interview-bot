"""Core interview flow: Question → Answer → Next Question."""

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
)
from app.services.audio_service import transcribe_audio
from app.core.exceptions import ForbiddenException
from app.utils.exceptions import (
    InvalidSessionStateError,
    QuestionsNotGeneratedError,
    SessionNotFoundError,
)
from app.services.resume_parser import extract_text_from_document
from app.utils.file_validation import validate_document_upload
from app.services.question_utils import (
    grade_objective_answer,
    public_question_view,
    question_marks,
    question_text as extract_question_text,
    question_time_seconds,
    question_type,
)


logger = logging.getLogger(__name__)


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

        session.questions = questions
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

        index = session.current_question_index
        raw_question = session.questions[index]
        view = public_question_view(
            raw_question,
            shuffle_seed=f"{session.session_id}:{index}",
        )

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
        )

    def submit_answer(
        self, session_id: UUID, answer: str, user_id: int
    ) -> AnswerSubmitResponse:
        session = self._get_session_for_user(session_id, user_id)

        if not session.questions:
            raise QuestionsNotGeneratedError()

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

        # Objective types graded server-side; subjective uses LLM judge
        raw_question = session.questions[index]
        try:
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

        self._maybe_send_candidate_report_email(
            session,
            candidate_email=candidate_email,
            candidate_name=candidate_name,
            adjusted_final_score=adjusted_final_score,
            integrity_level=integrity_level,
        )

        report_email_sent = candidate_report_email_already_sent(session.session_id)

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
            integrity_penalty_percent=integrity_penalty_percent,
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

        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)

        safe_ext = ext if ext in {".webm", ".mp4"} else ".webm"
        filename = f"{session_id}_recording{safe_ext}"
        path = upload_dir / filename
        path.write_bytes(video_bytes)

        if not update_recording_filename(session_id, filename):
            raise SessionNotFoundError(str(session_id))

        if safe_ext == ".webm":
            mp4_path = _convert_recording_to_mp4(str(path))
            if mp4_path:
                update_recording_mp4_filename(session_id, Path(mp4_path).name)

        return filename

    def resolve_recording_file(self, session_id: UUID) -> tuple[Path, str, str]:
        """Return recording path, media type, and download filename (MP4 then WebM)."""
        from app.services.session_persistence import (
            _get_recording_filename_async,
            _get_recording_mp4_filename_async,
            _run_async,
        )

        upload_dir = Path(settings.UPLOAD_DIR)

        mp4_filename = _run_async(_get_recording_mp4_filename_async(session_id))
        if mp4_filename:
            mp4_path = upload_dir / mp4_filename
            if mp4_path.is_file():
                return mp4_path, "video/mp4", "interview_recording.mp4"

        filename = _run_async(_get_recording_filename_async(session_id))
        if filename:
            webm_path = upload_dir / filename
            if webm_path.is_file():
                return webm_path, "video/webm", "interview_recording.webm"

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
        return pdf_bytes, candidate_report_filename(session, candidate_name=candidate_name)

    def _maybe_send_candidate_report_email(
        self,
        session: InterviewSession,
        *,
        candidate_email: str,
        candidate_name: str,
        adjusted_final_score: float | None,
        integrity_level: str | None,
    ) -> None:
        """Send the candidate PDF report once per session; never block interview completion."""
        from app.services.email_service import send_interview_report_email

        try:
            if candidate_report_email_already_sent(session.session_id):
                logger.info(
                    "[EMAIL] Candidate report already sent for session %s",
                    session.session_id,
                )
                return

            pdf_bytes, pdf_filename = self.get_candidate_report(
                session,
                candidate_name=candidate_name,
            )
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
                "[EMAIL] Failed to send candidate report for session %s: %s",
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
