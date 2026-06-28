import json
from app.core.config import settings
from app.core.exceptions import AIException
from app.judge.rubric import Rubric, get_rubric
from app.services.groq_client import get_groq_client
from typing import Optional

SYSTEM_PROMPT = """You are an expert technical interviewer acting as an impartial judge.
You evaluate candidate answers based on a provided rubric with specific criteria and weightages.
You return ONLY valid JSON. No markdown, no preamble, no extra text."""


def _chat(user_prompt: str) -> str:
    try:
        response = get_groq_client().chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        raise AIException(
            "Answer evaluation is temporarily unavailable. Please try again."
        ) from exc


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[start:end])


def judge_answer(
    question: str,
    answer: str,
    job_role: str,
    rubric: Optional[Rubric] = None,
    expected_answer: Optional[str] = None,
) -> dict:
    if rubric is None:
        rubric = get_rubric(job_role)

    criteria_text = "\n".join([
        f"- {c.name} (weight: {int(c.weight * 100)}%): {c.description}"
        for c in rubric.criteria
    ])

    expected_section = ""
    if expected_answer:
        expected_section = f"\nExpected Answer / Key Points:\n{expected_answer}\n"

    criteria_json = "\n".join([
        f'    "{c.name}": {{"score": 0, "reasoning": "one sentence"}}'
        for c in rubric.criteria
    ])

    prompt = f"""You are judging a candidate interview answer for a {job_role} role.

Question: {question}
{expected_section}
Candidate Answer: {answer}

Evaluation Rubric:
{criteria_text}

Score each criterion from 0 to 100, then calculate the weighted total.

Return ONLY this JSON:
{{
  "criteria_scores": {{
{criteria_json}
  }},
  "weighted_total": 0,
  "overall_reasoning": "2-3 sentence summary",
  "strengths": ["strength 1", "strength 2"],
  "improvements": ["improvement 1", "improvement 2"]
}}"""

    raw = _chat(prompt)
    result = _parse_json(raw)

    total = 0.0
    for c in rubric.criteria:
        score = result.get("criteria_scores", {}).get(c.name, {}).get("score", 0)
        total += score * c.weight
    result["weighted_total"] = round(total, 2)
    result["rubric_used"] = [{"name": c.name, "weight": c.weight} for c in rubric.criteria]

    return result


def judge_session(
    transcript: list[dict],
    job_role: str,
    rubric: Optional[Rubric] = None,
    expected_answers: Optional[list] = None,
) -> list[dict]:
    if rubric is None:
        rubric = get_rubric(job_role)

    results = []
    for i, item in enumerate(transcript):
        expected = expected_answers[i] if expected_answers and i < len(expected_answers) else None
        judgment = judge_answer(
            question=item["question"],
            answer=item["answer"],
            job_role=job_role,
            rubric=rubric,
            expected_answer=expected,
        )
        results.append({
            "index": i + 1,
            "question": item["question"],
            "answer": item["answer"],
            "judgment": judgment,
        })
    return results