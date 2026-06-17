from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.judge.judge import judge_session
from app.judge.final_score import compute_final_score
from app.judge.rubric import get_rubric

router = APIRouter(prefix="/judge", tags=["LLM Judge"])

judge_store: dict = {}


class TranscriptItem(BaseModel):
    question: str
    answer: str
    expected_answer: Optional[str] = None

class JudgeRequest(BaseModel):
    session_id: str
    candidate_name: str
    job_role: str
    transcript: list[TranscriptItem]
    custom_weights: Optional[dict[str, float]] = None
    recommendation_thresholds: Optional[dict[str, float]] = None


@router.post("/evaluate")
async def evaluate(req: JudgeRequest):
    if not req.transcript:
        raise HTTPException(status_code=400, detail="Transcript cannot be empty")

    if req.custom_weights:
        rubric = get_rubric(req.job_role)
        for c in rubric.criteria:
            if c.name in req.custom_weights:
                c.weight = req.custom_weights[c.name]
    else:
        rubric = get_rubric(req.job_role)

    transcript_dicts = [{"question": i.question, "answer": i.answer} for i in req.transcript]
    expected_answers = [i.expected_answer for i in req.transcript]

    judged_items = judge_session(
        transcript=transcript_dicts,
        job_role=req.job_role,
        rubric=rubric,
        expected_answers=expected_answers,
    )

    final = compute_final_score(judged_items, req.recommendation_thresholds)

    result = {
        "session_id": req.session_id,
        "candidate_name": req.candidate_name,
        "job_role": req.job_role,
        "judged_items": judged_items,
        "final": final,
    }

    judge_store[req.session_id] = result
    return result


@router.get("/result/{session_id}")
async def get_result(session_id: str):
    if session_id not in judge_store:
        raise HTTPException(status_code=404, detail="Session not found")
    return judge_store[session_id]


@router.get("/rubric")
async def get_default_rubric(role: Optional[str] = None):
    rubric = get_rubric(role)
    return {
        "role": role or "default",
        "criteria": [
            {"name": c.name, "description": c.description, "weight": c.weight}
            for c in rubric.criteria
        ]
    }