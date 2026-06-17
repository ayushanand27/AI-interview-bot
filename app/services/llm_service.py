"""Reusable OpenAI client for generating interview questions."""

import json
from typing import Optional

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

from app.core.config import get_settings
from app.core.exceptions import AIException


class LLMService:
    """Wraps OpenAI chat completions for technical interview content."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_MODEL

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
        """
        Generate concise technical interview questions.

        Returns a list of plain-text questions (one per interview step).
        """
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
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.7,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except (RateLimitError, APIConnectionError, APIError) as exc:
            raise AIException(
                "Question generation is temporarily unavailable. Please try again in a moment."
            ) from exc
        except Exception as exc:
            raise AIException(
                "Question generation failed. Please try again in a moment."
            ) from exc

        try:
            content = response.choices[0].message.content or "{}"
            payload = json.loads(content)
            questions = payload.get("questions", [])
        except (json.JSONDecodeError, IndexError, AttributeError) as exc:
            raise AIException(
                "Question generation returned an invalid response. Please try again."
            ) from exc

        if not isinstance(questions, list) or not questions:
            raise AIException("Question generation returned no questions. Please try again.")

        # Normalize and trim to requested count
        cleaned = [str(q).strip() for q in questions if str(q).strip()]
        return cleaned[:question_count]


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Lazy singleton so the app boots before OPENAI_API_KEY is set."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
