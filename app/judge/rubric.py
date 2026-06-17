from pydantic import BaseModel
from typing import Optional


class Criterion(BaseModel):
    name: str
    description: str
    weight: float


class Rubric(BaseModel):
    criteria: list[Criterion]

    def validate_weights(self) -> bool:
        total = sum(c.weight for c in self.criteria)
        return abs(total - 1.0) < 0.01


DEFAULT_RUBRIC = Rubric(
    criteria=[
        Criterion(name="Technical Accuracy", description="Is the answer factually correct and technically sound?", weight=0.40),
        Criterion(name="Completeness", description="Did the candidate cover all key aspects of the question?", weight=0.25),
        Criterion(name="Communication Clarity", description="Was the answer well structured, clear and easy to understand?", weight=0.20),
        Criterion(name="Depth and Insight", description="Did the candidate go beyond surface level and show deeper understanding?", weight=0.15),
    ]
)

RUBRIC_PRESETS = {
    "frontend": Rubric(criteria=[
        Criterion(name="Technical Accuracy", description="Correct use of frontend concepts, frameworks, browser APIs.", weight=0.35),
        Criterion(name="Completeness", description="Covered all key aspects of the question.", weight=0.20),
        Criterion(name="Communication Clarity", description="Clear and structured explanation.", weight=0.30),
        Criterion(name="Depth and Insight", description="Showed deeper understanding beyond basics.", weight=0.15),
    ]),
    "backend": Rubric(criteria=[
        Criterion(name="Technical Accuracy", description="Correct understanding of backend systems, APIs, databases.", weight=0.40),
        Criterion(name="Completeness", description="Covered all key aspects of the question.", weight=0.25),
        Criterion(name="Communication Clarity", description="Clear and structured explanation.", weight=0.20),
        Criterion(name="Depth and Insight", description="Showed deeper understanding beyond basics.", weight=0.15),
    ]),
    "ml": Rubric(criteria=[
        Criterion(name="Technical Accuracy", description="Correct ML/AI concepts and terminology.", weight=0.45),
        Criterion(name="Completeness", description="Covered all key aspects of the question.", weight=0.25),
        Criterion(name="Communication Clarity", description="Clear explanation of complex concepts.", weight=0.15),
        Criterion(name="Depth and Insight", description="Showed research-level or practical depth.", weight=0.15),
    ]),
}


def get_rubric(role: Optional[str] = None) -> Rubric:
    if role:
        role_lower = role.lower()
        for key in RUBRIC_PRESETS:
            if key in role_lower:
                return RUBRIC_PRESETS[key]
    return DEFAULT_RUBRIC