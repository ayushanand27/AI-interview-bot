"""Recruiter assessment creation routes (JD-based invites)."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.common import BaseResponse
from app.schemas.recruiter_assessment import (
    AssessmentQuestion,
    AssessmentSummary,
    CreateAssessmentRequest,
    CreateAssessmentResponse,
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    ParseJdPdfResponse,
    UpdateAssessmentRequest,
)
from app.services.assessment_service import AssessmentService
from app.services.interview_service import resolve_job_description
from app.services.resume_parser import extract_text_from_document
from app.utils.file_validation import validate_document_upload
from app.utils.validation_errors import serializable_validation_errors

router = APIRouter(prefix="/recruiter", tags=["Recruiter Assessment"])


def _parse_questions_form(questions_json: str | None) -> list[AssessmentQuestion] | None:
    if questions_json is None or not str(questions_json).strip():
        return None
    try:
        payload = json.loads(questions_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="questions must be valid JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=422, detail="questions must be a JSON array")
    try:
        return [AssessmentQuestion.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=serializable_validation_errors(exc)
        ) from exc


@router.post(
    "/generate-questions",
    response_model=BaseResponse[GenerateQuestionsResponse],
    summary="Generate draft interview questions from a JD (no invite created)",
)
async def generate_questions(
    question_count: int = Form(...),
    difficulty: str = Form(...),
    jd_text: str = Form(""),
    question_types: str | None = Form(None),
    jd_pdf: UploadFile | None = File(None),
    _current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    jd_pdf_bytes: bytes | None = None
    if jd_pdf is not None and jd_pdf.filename:
        jd_pdf_bytes = await jd_pdf.read()

    try:
        combined_jd = resolve_job_description(
            jd_text,
            jd_pdf_bytes,
            pdf_filename=jd_pdf.filename if jd_pdf else None,
            pdf_content_type=jd_pdf.content_type if jd_pdf else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed_types = None
    if question_types and question_types.strip():
        try:
            parsed_types = json.loads(question_types)
        except json.JSONDecodeError:
            parsed_types = [p.strip() for p in question_types.split(",") if p.strip()]

    try:
        data = GenerateQuestionsRequest(
            jd_text=combined_jd,
            question_count=question_count,
            difficulty=difficulty,
            question_types=parsed_types,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=serializable_validation_errors(exc)
        ) from exc

    result = AssessmentService.generate_questions_preview(data)
    return BaseResponse(
        success=True,
        message=f"Generated {len(result.questions)} question(s)",
        data=result,
    )


@router.post(
    "/create-assessment",
    response_model=BaseResponse[CreateAssessmentResponse],
    summary="Create a JD-based interview assessment and invite link",
)
async def create_assessment(
    question_count: int = Form(...),
    difficulty: str = Form(...),
    expiry_hours: int = Form(...),
    jd_text: str = Form(""),
    jd_pdf: UploadFile | None = File(None),
    questions: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    jd_pdf_bytes: bytes | None = None
    if jd_pdf is not None and jd_pdf.filename:
        jd_pdf_bytes = await jd_pdf.read()

    try:
        combined_jd = resolve_job_description(
            jd_text,
            jd_pdf_bytes,
            pdf_filename=jd_pdf.filename if jd_pdf else None,
            pdf_content_type=jd_pdf.content_type if jd_pdf else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    custom_questions = _parse_questions_form(questions)

    try:
        data = CreateAssessmentRequest(
            jd_text=combined_jd,
            question_count=question_count
            if custom_questions is None
            else len(custom_questions),
            difficulty=difficulty,
            expiry_hours=expiry_hours,
            questions=custom_questions,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=serializable_validation_errors(exc)
        ) from exc

    service = AssessmentService(db)
    result = await service.create_assessment(current_user.id, data)
    return BaseResponse(
        success=True,
        message="Assessment created successfully",
        data=result,
    )


@router.post(
    "/parse-jd-pdf",
    response_model=BaseResponse[ParseJdPdfResponse],
    summary="Extract job description text from an uploaded document",
)
async def parse_jd_pdf(
    # Frontend sends multipart field name "pdf" (PDF, Word, or TXT).
    pdf: UploadFile = File(...),
    _current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    filename = pdf.filename or "job-description.pdf"
    file_bytes = await pdf.read()
    validate_document_upload(file_bytes, pdf.content_type, filename)
    jd_text = extract_text_from_document(file_bytes, filename)
    return BaseResponse(
        success=True,
        message="Job description extracted successfully",
        data=ParseJdPdfResponse(jd_text=jd_text),
    )


@router.get(
    "/assessments",
    response_model=BaseResponse[list[AssessmentSummary]],
    summary="List assessments created by the current recruiter",
)
async def list_assessments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = AssessmentService(db)
    assessments = await service.list_assessments(current_user.id)
    return BaseResponse(
        success=True,
        message=f"Found {len(assessments)} assessment(s)",
        data=assessments,
    )


@router.delete(
    "/assessments/{token}",
    response_model=BaseResponse[None],
    summary="Delete an unused assessment invite",
)
async def delete_assessment(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = AssessmentService(db)
    await service.delete_assessment(current_user.id, token)
    return BaseResponse(success=True, message="Assessment deleted", data=None)


@router.patch(
    "/assessments/{token}",
    response_model=BaseResponse[AssessmentSummary],
    summary="Update assessment settings (e.g. extend expiry)",
)
async def update_assessment(
    token: str,
    body: UpdateAssessmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = AssessmentService(db)
    updated = await service.update_assessment(current_user.id, token, body)
    return BaseResponse(
        success=True,
        message="Assessment updated",
        data=updated,
    )
