"""Interview question generation via Groq (configurable model + API key)."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.core.config import get_settings
from app.core.exceptions import AIException
from app.services.assessment_service import _parse_questions_from_llm_text
from app.services.groq_client import groq_chat_completion


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
    ) -> list[dict[str, Any]]:
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
            response = groq_chat_completion(
                model=self._model,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content or ""
        except AIException:
            raise
        except Exception as exc:
            raise AIException(
                "Generation failed. Please try again."
            ) from exc

        if not content.strip():
            raise AIException("Generation failed. Please try again.")

        jd_hint = job_description or resume_text or role_title
        # Mock/candidate interviews are oral/subjective; recruiter assessments
        # pass their own question_types via assessment_service.
        questions = _parse_questions_from_llm_text(
            content,
            question_count,
            jd_hint,
            experience_level,
            ["subjective"],
        )

        if not questions:
            raise AIException("Generation failed. Please try again.")

        return questions[:question_count]

    def generate_follow_up_question(
        self,
        *,
        role_title: str,
        experience_level: str,
        topic: str,
        competency: str,
        mode: str,
        weak_area: str,
        prior_question: str,
        prior_answer: str,
        job_description: Optional[str] = None,
        resume_text: Optional[str] = None,
    ) -> str:
        """Generate one adaptive follow-up for Phase 5 interviewing."""
        mode_guidance = {
            "scaffold": "Ask a simpler clarifying question that helps the candidate show basics.",
            "go_deeper": "Ask a deeper, more advanced follow-up that probes expertise.",
            "probe_gap": "Ask a targeted question that covers an uncovered competency or topic.",
        }.get(mode, "Ask a focused follow-up that improves topic coverage.")

        resume_section = (
            f"Candidate resume excerpt:\n{(resume_text or '')[:1200]}\n"
            if resume_text and resume_text.strip()
            else ""
        )
        job_section = (
            f"Job description excerpt:\n{(job_description or '')[:1200]}\n"
            if job_description and job_description.strip()
            else ""
        )

        system_prompt = (
            "You are a senior technical interviewer running an adaptive live interview. "
            "Return ONLY valid JSON with a single follow-up question. "
            "Do not include numbering, markdown, or answer keys."
        )
        user_prompt = (
            f"Role: {role_title}\n"
            f"Target difficulty: {experience_level}\n"
            f"Topic focus: {topic}\n"
            f"Competency to assess: {competency}\n"
            f"Adaptation mode: {mode} — {mode_guidance}\n"
            f"Weak / focus area from prior answer: {weak_area}\n\n"
            f"Prior question:\n{prior_question}\n\n"
            f"Candidate answer:\n{prior_answer[:1500]}\n\n"
            f"{resume_section}"
            f"{job_section}\n"
            "Constraints:\n"
            "- One question only, answerable in 2-4 minutes.\n"
            "- Must be distinct from the prior question.\n"
            "- Stay relevant to the role and chosen topic.\n\n"
            'Return ONLY JSON: {"question": "..."}\n'
        )

        try:
            response = groq_chat_completion(
                model=self._model,
                temperature=0.6,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content or ""
        except AIException:
            raise
        except Exception as exc:
            raise AIException("Generation failed. Please try again.") from exc

        text = content.strip()
        if not text:
            raise AIException("Generation failed. Please try again.")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    payload = json.loads(text[start:end])
                except json.JSONDecodeError:
                    payload = {}
            else:
                payload = {}

        if isinstance(payload, dict):
            for key in ("question", "text", "follow_up"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        # Fallback: treat raw content as the question if JSON parsing failed.
        cleaned = re.sub(r'^["\']|["\']$', "", text.strip())
        cleaned = re.sub(r"^\d+[\).\s]+", "", cleaned).strip()
        if cleaned:
            return cleaned
        raise AIException("Generation failed. Please try again.")


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
