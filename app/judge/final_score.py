from typing import Optional


RECOMMENDATION_THRESHOLDS = {
    "Strong Hire": 85,
    "Hire": 70,
    "Maybe": 50,
    "No Hire": 0,
}


def get_recommendation(score: float, thresholds: Optional[dict] = None) -> str:
    t = thresholds or RECOMMENDATION_THRESHOLDS
    if score >= t["Strong Hire"]:
        return "Strong Hire"
    elif score >= t["Hire"]:
        return "Hire"
    elif score >= t["Maybe"]:
        return "Maybe"
    else:
        return "No Hire"


def compute_final_score(judged_items: list[dict], thresholds: Optional[dict] = None) -> dict:
    if not judged_items:
        return {"final_score": 0, "recommendation": "No Hire", "per_question_scores": []}

    total = 0.0
    per_question = []
    all_strengths = []
    all_improvements = []

    for item in judged_items:
        j = item["judgment"]
        score = j.get("weighted_total", 0)
        total += score
        per_question.append({
            "index": item["index"],
            "question": item["question"],
            "score": score,
            "reasoning": j.get("overall_reasoning", ""),
        })
        all_strengths.extend(j.get("strengths", []))
        all_improvements.extend(j.get("improvements", []))

    avg_score = round(total / len(judged_items), 2)
    recommendation = get_recommendation(avg_score, thresholds)

    seen_s, seen_i = set(), set()
    unique_strengths, unique_improvements = [], []
    for s in all_strengths:
        if s not in seen_s:
            seen_s.add(s)
            unique_strengths.append(s)
    for imp in all_improvements:
        if imp not in seen_i:
            seen_i.add(imp)
            unique_improvements.append(imp)

    return {
        "final_score": avg_score,
        "recommendation": recommendation,
        "per_question_scores": per_question,
        "top_strengths": unique_strengths[:4],
        "top_improvements": unique_improvements[:4],
        "score_breakdown": {
            "max_possible": 100,
            "candidate_score": avg_score,
            "thresholds": thresholds or RECOMMENDATION_THRESHOLDS,
        }
    }