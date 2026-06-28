"""Interview question generation via Groq (configurable model + API key)."""

from __future__ import annotations

import json
from typing import Optional

from groq import APIConnectionError, APIError, RateLimitError

from app.core.config import get_settings
from app.core.exceptions import AIException
from app.services.assessment_service import _parse_questions_from_llm_text
from app.services.groq_client import get_groq_client


class LLMService:
    """Generates mock-interview questions from resume + job description."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.GROQ_MODEL

    def generate_interview_questions(
        self,
        *,
        role_title: str,
        experience_level: str,
        question_count: int,
        topic_focus: Optional[str] = None,
        resume_text: Optional[str] = None,
        job_description: Optional[str] = None,
    ) -> list[str]:
        focus_line = (
            f"Focus topics: {topic_focus}."
            if topic_focus
            else "Cover a balanced mix of fundamentals and practical scenarios."
        )

        resume_section = (
            f"Candidate Resume (extracted text):\n{resume_text.strip()}\n"
            if resume_text and resume_text.strip()
            else "Candidate Resume: not provided.\n"
        )

        job_section = (
            f"Job Description:\n{job_description.strip()}\n"
            if job_description and job_description.strip()
            else "Job Description: not provided.\n"
        )

        system_prompt = (
            "You are a senior technical interviewer. "
            "Generate clear, concise interview questions suitable for a live interview. "
            "Each question must be answerable in 2-4 minutes. "
            "Do not include numbering prefixes in the question text."
        )

        user_prompt = (
            f"Role: {role_title}\n"
            f"Experience level: {experience_level}\n"
            f"Number of questions: {question_count}\n"
            f"{focus_line}\n\n"
            f"{resume_section}\n"
            f"{job_section}\n"
            "Use the resume and job description to tailor questions to the candidate's background, "
            "highlight likely strengths, and explore gaps relevant to the target role.\n\n"
            "Return ONLY valid JSON in this shape:\n"
            '{"questions": ["question 1", "question 2"]}'
        )

        try:
            response = get_groq_client().chat.completions.create(
                model=self._model,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content or ""
        except (RateLimitError, APIConnectionError, APIError) as exc:
            raise AIException(
                "Question generation is temporarily unavailable. Please try again in a moment."
            ) from exc
        except Exception as exc:
            raise AIException(
                "Question generation failed. Please try again in a moment."
            ) from exc

        if not content.strip():
            raise AIException("Question generation returned no questions. Please try again.")

        jd_hint = job_description or resume_text or role_title
        questions = _parse_questions_from_llm_text(
            content,
            question_count,
            jd_hint,
            experience_level,
        )

        if not questions:
            raise AIException("Question generation returned no questions. Please try again.")

        return questions[:question_count]


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
