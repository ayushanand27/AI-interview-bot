"""Interview session API endpoints."""

from typing import Annotated, Union
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, Query, Request, UploadFile, status, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_session_owner
from app.db.candidate_verification_model import CandidateVerification
from app.db.session import get_db
from app.db.session_model import Session as DBSession
from app.models.user import UserRole
from app.core.limiter import INTERVIEW_LIMIT, limiter
from app.models.user import User

from app.models.schemas import (
    AnswerSubmitRequest,
    AnswerSubmitResponse,
    AudioAnswerResponse,
    AudioTranscribeResponse,
    CodingAnswerRequest,
    CodingRunPublicRequest,
    CodingRunPublicResponse,
    CurrentQuestionResponse,
    EndInterviewResponse,
    FetchJdUrlRequest,
    FetchJdUrlResponse,
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    InterviewSessionResponse,
    RecordingUploadResponse,
)
from app.services.interview_service import interview_service, resolve_job_description
from app.services.session_persistence import abandon_active_sessions_for_user_async
from app.services.jd_scraper import fetch_jd_from_url
from app.services.resume_parser import extract_text_from_document
from app.utils.file_validation import validate_document_upload
from app.core.exceptions import AppException, ForbiddenException

router = APIRouter(prefix="/interviews", tags=["Interviews"])

ALLOWED_AUDIO_EXTENSIONS = {".webm", ".mp4", ".wav", ".mpeg", ".mp3", ".m4a", ".ogg"}
ALLOWED_VIDEO_EXTENSIONS = {".webm", ".mp4"}

# Swagger shows a placeholder UUID by default — always paste the real id from POST /sessions.
SessionId = Annotated[
    UUID,
    Path(
        description=(
            "Session UUID returned by **POST /api/v1/interviews/sessions** "
            "(do not use the Swagger placeholder example)."
        ),
    ),
]


@router.post(
    "/reset-active-session",
    summary="Clear stuck active interview sessions",
    description=(
        "Marks all in-progress sessions for the current candidate as abandoned "
        "so a new interview can be started."
    ),
)
@limiter.limit(INTERVIEW_LIMIT)
async def reset_active_session(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    await abandon_active_sessions_for_user_async(current_user.id)
    return interview_service.reset_active_sessions(current_user.id)


@router.post(
    "/fetch-jd-url",
    response_model=FetchJdUrlResponse,
    summary="Extract job description text from a job posting URL",
)
@limiter.limit(INTERVIEW_LIMIT)
async def fetch_jd_url(
    request: Request,
    payload: FetchJdUrlRequest,
    current_user: User = Depends(get_current_user),
) -> FetchJdUrlResponse:
    jd_text, source = await fetch_jd_from_url(payload.url)
    return FetchJdUrlResponse(jd_text=jd_text, source=source)


@router.post(
    "/sessions",
    response_model=InterviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create interview session",
    description="Creates a new interview session with a UUID. Questions are not generated yet.",
)
@limiter.limit(INTERVIEW_LIMIT)
async def create_session(
    request: Request,
    role_title: str = Form("Software Engineer"),
    experience_level: str = Form("mid"),
    topic_focus: str | None = Form(None),
    job_description: str = Form(""),
    job_description_pdf: UploadFile | None = File(None),
    resume_pdf: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> InterviewSessionResponse:
    if current_user.role == UserRole.CANDIDATE and not current_user.is_verified:
        raise ForbiddenException(
            "Please verify your email before starting an interview."
        )

    filename = resume_pdf.filename or "resume.pdf"
    resume_bytes = await resume_pdf.read()
    try:
        validate_document_upload(resume_bytes, resume_pdf.content_type, filename)
        resume_text = extract_text_from_document(resume_bytes, filename)
    except AppException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    jd_pdf_bytes: bytes | None = None
    if job_description_pdf is not None and job_description_pdf.filename:
        jd_pdf_bytes = await job_description_pdf.read()

    try:
        resolved_jd = resolve_job_description(
            job_description,
            jd_pdf_bytes,
            pdf_filename=job_description_pdf.filename if job_description_pdf else None,
            pdf_content_type=job_description_pdf.content_type if job_description_pdf else None,
        )
    except AppException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await abandon_active_sessions_for_user_async(current_user.id)
    return interview_service.create_session(
        user_id=current_user.id,
        role_title=role_title,
        experience_level=experience_level,
        topic_focus=topic_focus,
        resume_filename=filename,
        resume_text=resume_text,
        job_description=resolved_jd,
    )


@router.post(
    "/sessions/{session_id}/questions",
    response_model=GenerateQuestionsResponse,
    summary="Generate interview questions",
    description=(
        "Uses Groq to generate technical questions for this session. "
        "Use the `session_id` from your create-session response."
    ),
)
@limiter.limit(INTERVIEW_LIMIT)
def generate_questions(
    request: Request,
    session_id: SessionId,
    payload: GenerateQuestionsRequest | None = None,
    current_user: User = Depends(get_current_user),
) -> GenerateQuestionsResponse:
    body = payload or GenerateQuestionsRequest()
    return interview_service.generate_questions(
        session_id,
        current_user.id,
        question_count=body.question_count,
    )


@router.get(
    "/sessions/{session_id}/current-question",
    response_model=CurrentQuestionResponse,
    summary="Get current question",
    description="Returns exactly ONE question at a time based on current index.",
)
@limiter.limit(INTERVIEW_LIMIT)
def get_current_question(
    request: Request,
    session_id: SessionId,
    current_user: User = Depends(get_current_user),
) -> CurrentQuestionResponse:
    return interview_service.get_current_question(session_id, current_user.id)


@router.post(
    "/sessions/{session_id}/answers",
    response_model=AnswerSubmitResponse,
    summary="Submit answer",
    description=(
        "Stores the answer for the current question and advances the index. "
        "If has_more_questions is true, you must call GET /current-question before answering again."
    ),
)
@limiter.limit(INTERVIEW_LIMIT)
def submit_answer(
    request: Request,
    session_id: SessionId,
    payload: AnswerSubmitRequest,
    current_user: User = Depends(get_current_user),
) -> AnswerSubmitResponse:
    return interview_service.submit_answer(
        session_id, payload.answer, current_user.id
    )


@router.post(
    "/sessions/{session_id}/coding/run-public",
    response_model=CodingRunPublicResponse,
    summary="Run coding public tests",
    description=(
        "Executes candidate source against public sample tests via Judge0. "
        "Does not advance the interview or score hidden tests."
    ),
)
@limiter.limit(INTERVIEW_LIMIT)
def run_coding_public_tests(
    request: Request,
    session_id: SessionId,
    payload: CodingRunPublicRequest,
    current_user: User = Depends(get_current_user),
) -> CodingRunPublicResponse:
    result = interview_service.run_coding_public_tests(
        session_id,
        current_user.id,
        language=payload.language,
        source=payload.source,
    )
    return CodingRunPublicResponse(**result)


@router.post(
    "/sessions/{session_id}/coding/answers",
    response_model=AnswerSubmitResponse,
    summary="Submit coding answer",
    description=(
        "Stores source code, grades against hidden tests via Judge0, "
        "and advances the interview like POST /answers."
    ),
)
@limiter.limit(INTERVIEW_LIMIT)
def submit_coding_answer(
    request: Request,
    session_id: SessionId,
    payload: CodingAnswerRequest,
    current_user: User = Depends(get_current_user),
) -> AnswerSubmitResponse:
    return interview_service.submit_coding_answer(
        session_id,
        current_user.id,
        language=payload.language,
        source=payload.source,
    )


@router.post(
    "/sessions/{session_id}/audio-answer",
    response_model=Union[AudioTranscribeResponse, AudioAnswerResponse],
    summary="Transcribe or submit audio answer",
    description=(
        "Upload audio (webm, mp4, wav). By default (`submit=false`) only transcribes "
        "via Whisper for review. Set `submit=true` to transcribe, judge, and store "
        "the answer like POST /answers."
    ),
)
@limiter.limit(INTERVIEW_LIMIT)
async def submit_audio_answer(
    request: Request,
    session_id: SessionId,
    audio: UploadFile = File(...),
    submit: bool = Form(
        False,
        description="If true, transcribe and immediately submit/judge the answer.",
    ),
    current_user: User = Depends(get_current_user),
) -> AudioTranscribeResponse | AudioAnswerResponse:
    filename = audio.filename or "recording.webm"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".webm"
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}",
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    try:
        interview_service.verify_session_access(session_id, current_user.id)
        if submit:
            return interview_service.submit_audio_answer(
                session_id,
                audio_bytes,
                current_user.id,
                filename=filename,
            )
        from app.services.audio_service import transcribe_audio

        transcribed = transcribe_audio(audio_bytes, filename=filename)
        return AudioTranscribeResponse(
            session_id=session_id,
            transcribed_text=transcribed,
        )
    except AppException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Audio transcription failed: {exc}",
        ) from exc


@router.post(
    "/sessions/{session_id}/end",
    response_model=EndInterviewResponse,
    summary="End interview session",
    description=(
        "Marks the session ended and returns stored questions and answers. "
        "You can end early, but unanswered questions will show in unanswered_count."
    ),
)
@limiter.limit(INTERVIEW_LIMIT)
def end_interview(
    request: Request,
    session_id: SessionId,
    current_user: User = Depends(get_current_user),
) -> EndInterviewResponse:
    return interview_service.end_interview(
        session_id,
        current_user.id,
        candidate_email=current_user.email,
        candidate_name=current_user.full_name,
    )


@router.post(
    "/sessions/{session_id}/recording",
    response_model=RecordingUploadResponse,
    summary="Upload interview session recording",
    description="Upload webcam+audio recording for recruiter verification.",
)
@limiter.limit(INTERVIEW_LIMIT)
async def upload_session_recording(
    request: Request,
    session_id: SessionId,
    # Frontend must send: formData.append("video", blob, "recording.webm")
    video: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> RecordingUploadResponse:
    filename = video.filename or "recording.webm"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".webm"
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format. Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}",
        )

    video_bytes = await video.read()
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Recording file is empty")

    try:
        saved = interview_service.save_session_recording(
            session_id,
            video_bytes,
            current_user.id,
            ext=ext,
        )
        return RecordingUploadResponse(
            session_id=session_id,
            recording_filename=saved,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}/recording",
    summary="Download interview session recording",
    description=(
        "Recruiters may access recordings for sessions started via their invite links. "
        "Candidates may only access recordings for sessions they own."
    ),
)
@limiter.limit(INTERVIEW_LIMIT)
async def get_session_recording(
    request: Request,
    session_id: SessionId,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_recruiter = current_user.role == UserRole.RECRUITER
    if is_recruiter:
        from app.services.recruiter_service import RecruiterService

        owns = await RecruiterService(db).recruiter_owns_session(
            current_user.id, session_id
        )
        if not owns:
            raise HTTPException(status_code=404, detail="Recording not available")
    else:
        interview_service.verify_session_access(session_id, current_user.id)

    try:
        path, media_type, download_name = interview_service.resolve_recording_file(
            session_id
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recording not available") from None
    except Exception:
        raise HTTPException(status_code=404, detail="Recording not available") from None

    return FileResponse(
        path,
        media_type=media_type,
        filename=download_name,
    )


async def _candidate_report_context(
    db: AsyncSession,
    session_id: UUID,
) -> tuple[str | None, int | None, object | None]:
    verification_result = await db.execute(
        select(CandidateVerification).where(
            CandidateVerification.session_id == str(session_id)
        )
    )
    verification = verification_result.scalar_one_or_none()
    row = await db.get(DBSession, session_id)
    duration_minutes = None
    interview_date = None
    if row is not None:
        interview_date = row.updated_at
        if row.created_at and row.updated_at:
            duration_minutes = max(
                int((row.updated_at - row.created_at).total_seconds() // 60),
                1,
            )
    candidate_name = verification.candidate_name if verification else None
    return candidate_name, duration_minutes, interview_date


@router.get(
    "/sessions/{session_id}/my-recording",
    summary="Download candidate's own interview recording",
)
@limiter.limit(INTERVIEW_LIMIT)
async def get_my_recording(
    request: Request,
    session_id: SessionId,
    token: str | None = Query(None, description="Optional invite token"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_session_owner(session_id, db, current_user=current_user, token=token)
    try:
        path, media_type, download_name = interview_service.resolve_recording_file(
            session_id
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="Recording not available yet"
        ) from None
    except Exception:
        raise HTTPException(
            status_code=404, detail="Recording not available yet"
        ) from None

    return FileResponse(
        path,
        media_type=media_type,
        filename=download_name,
    )


@router.get(
    "/sessions/{session_id}/my-report",
    summary="Download candidate personal interview PDF report",
    description=(
        "Returns a candidate-friendly PDF for the session owner. Does not include "
        "hire/no-hire decisions or internal proctoring violation details."
    ),
)
@limiter.limit(INTERVIEW_LIMIT)
async def get_my_report(
    request: Request,
    session_id: SessionId,
    token: str | None = Query(None, description="Optional invite token"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_session_owner(
        session_id, db, current_user=current_user, token=token
    )
    candidate_name, duration_minutes, interview_date = await _candidate_report_context(
        db, session_id
    )
    try:
        pdf_bytes, filename = interview_service.get_candidate_report(
            session,
            candidate_name=candidate_name,
            duration_minutes=duration_minutes,
            interview_date=interview_date,
        )
    except AppException:
        raise
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
