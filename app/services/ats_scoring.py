"""Free-tier ATS scoring — structure hygiene + JD keyword match (no torch).

Inspired by ResumeMatch (ats-checker) Layer 1 + keyword analysis, adapted to
raw resume text so SmartSkale does not depend on sentence-transformers.
"""

from __future__ import annotations

import re
from typing import Any

# Structure weight 35% + keyword weight 65% (ResumeMatch-style blend).
STRUCTURE_WEIGHT = 0.35
KEYWORD_WEIGHT = 0.65

# Synonym groups ported from ResumeMatch (ats-checker) skill_aliases — CPU-only.
ALIAS_GROUPS: list[frozenset[str]] = [
    frozenset({"ml", "machine learning"}),
    frozenset({"ai", "artificial intelligence"}),
    frozenset({"nlp", "natural language processing"}),
    frozenset({"sql", "structured query language"}),
    frozenset({"power bi", "powerbi", "microsoft power bi"}),
    frozenset({"excel", "microsoft excel", "ms excel"}),
    frozenset({"aws", "amazon web services"}),
    frozenset({"gcp", "google cloud", "google cloud platform"}),
    frozenset({"ci/cd", "cicd", "continuous integration", "continuous deployment"}),
    frozenset({"js", "javascript"}),
    frozenset({"ts", "typescript"}),
    frozenset({"k8s", "kubernetes"}),
    frozenset({"rest", "rest api", "restful", "restful api"}),
    frozenset({"seo", "search engine optimization"}),
    frozenset({"ui", "user interface"}),
    frozenset({"ux", "user experience"}),
    frozenset({"etl", "extract transform load"}),
    frozenset({"bi", "business intelligence"}),
    frozenset({"salesforce", "salesforce crm", "sfdc"}),
    frozenset({"power automate", "microsoft power automate", "powerautomate"}),
    frozenset({"rag", "retrieval augmented generation"}),
    frozenset({"llm", "large language model", "large language models"}),
    frozenset({"api", "apis", "application programming interface"}),
    frozenset({"oop", "object oriented programming", "object-oriented programming"}),
    frozenset({"tcp/ip", "tcp ip", "tcpip"}),
    frozenset({"fastapi", "fast api"}),
    frozenset({"postgres", "postgresql", "psql"}),
    frozenset({"react", "reactjs", "react.js"}),
    frozenset({"node", "nodejs", "node.js"}),
    frozenset({"docker", "containers"}),
    frozenset({"python", "py"}),
    frozenset({"java", "jvm"}),
    frozenset({"c++", "cpp"}),
]

_COMMON_SKILLS = [
    "python", "java", "javascript", "typescript", "react", "node", "fastapi",
    "django", "flask", "spring", "sql", "postgres", "mysql", "mongodb",
    "redis", "aws", "gcp", "azure", "docker", "kubernetes", "ci/cd",
    "git", "linux", "rest", "graphql", "kafka", "spark", "pandas",
    "numpy", "machine learning", "llm", "rag", "next.js", "vue",
    "angular", "go", "golang", "rust", "c++", "html", "css", "tailwind",
    "terraform", "ansible", "jenkins", "github actions", "s3", "lambda",
    "microservices", "system design", "oop", "dsa", "algorithms",
    "power bi", "excel", "etl", "salesforce", "seo", "ui", "ux",
]

SECTION_PATTERNS = {
    "experience": r"\b(experience|work history|employment|professional experience)\b",
    "education": r"\b(education|academic|university|bachelor|master|b\.?tech|m\.?tech)\b",
    "skills": r"\b(skills|technical skills|technologies|tech stack)\b",
    "summary": r"\b(summary|profile|objective|about me)\b",
    "projects": r"\b(projects|personal projects|selected projects)\b",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _alias_lookup() -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}
    for group in ALIAS_GROUPS:
        norm = {s.lower().strip() for s in group}
        for term in norm:
            lookup[term] = norm - {term}
    return lookup


def _keyword_in_text(keyword: str, haystack: str) -> bool:
    kw = re.escape(keyword.lower().strip())
    if not kw:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){kw}(?![a-z0-9])", haystack, re.I))


def extract_skills_from_jd(jd_text: str) -> list[str]:
    """Pull likely skills from JD using a curated vocabulary + aliases."""
    text = _normalize(jd_text)
    found: list[str] = []
    seen: set[str] = set()
    lookup = _alias_lookup()
    candidates = list(_COMMON_SKILLS)
    for group in ALIAS_GROUPS:
        candidates.extend(sorted(group))
    for skill in candidates:
        key = skill.lower().strip()
        if key in seen:
            continue
        if _keyword_in_text(skill, text):
            seen.add(key)
            found.append(skill)
            for alias in lookup.get(key, ()):
                seen.add(alias)
    return found[:40]


def _structure_score(resume_text: str) -> dict[str, Any]:
    raw = resume_text or ""
    text = _normalize(raw)
    word_count = len(raw.split())
    checks: list[dict[str, Any]] = []

    has_email = bool(re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", text))
    checks.append({
        "name": "Contact email",
        "passed": has_email,
        "reason": "Email found" if has_email else "No email detected",
        "weight": 15,
        "score": 15 if has_email else 0,
    })

    has_phone = bool(re.search(r"(\+?\d[\d\s\-()]{8,}\d)", raw))
    has_link = "linkedin" in text or "github" in text
    checks.append({
        "name": "Phone or professional link",
        "passed": has_phone or has_link,
        "reason": "Phone or LinkedIn/GitHub found" if (has_phone or has_link) else "Add phone or LinkedIn/GitHub",
        "weight": 10,
        "score": 10 if (has_phone or has_link) else 0,
    })

    sections_found = [
        name for name, pat in SECTION_PATTERNS.items() if re.search(pat, text, re.I)
    ]
    required = {"experience", "education", "skills"}
    missing = sorted(required - set(sections_found))
    core_ok = not missing
    checks.append({
        "name": "Core sections",
        "passed": core_ok,
        "reason": (
            "Experience, Education, and Skills signals detected"
            if core_ok
            else f"Missing section signals: {', '.join(missing)}"
        ),
        "weight": 30,
        "score": 30 if core_ok else max(0, 30 - 10 * len(missing)),
    })

    length_ok = 100 <= word_count <= 1500
    checks.append({
        "name": "Length sanity",
        "passed": length_ok,
        "reason": f"Resume length {word_count} words",
        "weight": 20,
        "score": 20 if length_ok else 8,
    })

    alnum = sum(1 for c in raw if c.isalnum())
    ratio = (alnum / len(raw)) if raw else 0.0
    parse_ok = ratio >= 0.45
    checks.append({
        "name": "Parse quality",
        "passed": parse_ok,
        "reason": f"Alphanumeric ratio {ratio:.0%}",
        "weight": 15,
        "score": round(15 * min(1.0, max(0.0, (ratio - 0.4) / 0.4)), 1),
    })

    has_extra = bool({"summary", "projects"} & set(sections_found))
    checks.append({
        "name": "Summary or Projects",
        "passed": has_extra,
        "reason": "Summary/Projects found" if has_extra else "Consider adding Summary or Projects",
        "weight": 10,
        "score": 10 if has_extra else 0,
    })

    total_w = sum(c["weight"] for c in checks) or 1
    earned = sum(c["score"] for c in checks)
    return {
        "score": round((earned / total_w) * 100, 1),
        "checks": checks,
        "sections_found": sections_found,
        "word_count": word_count,
    }


def _keyword_score(resume_text: str, jd_skills: list[str]) -> dict[str, Any]:
    corpus = _normalize(resume_text)
    lookup = _alias_lookup()
    if not jd_skills:
        return {
            "score": 0.0,
            "matched": [],
            "missing": [],
            "jd_skills": [],
        }

    matched: list[dict[str, Any]] = []
    missing: list[str] = []
    total = 0.0
    earned = 0.0
    for skill in jd_skills:
        key = skill.lower().strip()
        total += 1.0
        hit = _keyword_in_text(skill, corpus)
        match_type = "exact"
        if not hit:
            for alias in lookup.get(key, ()):
                if _keyword_in_text(alias, corpus):
                    hit = True
                    match_type = "synonym"
                    break
        if hit:
            earned += 1.0 if match_type == "exact" else 0.8
            matched.append({"keyword": skill, "match_type": match_type})
        else:
            missing.append(skill)

    return {
        "score": round((earned / total) * 100, 1) if total else 0.0,
        "matched": matched,
        "missing": missing,
        "jd_skills": jd_skills,
    }


def score_resume_against_jd(
    resume_text: str,
    jd_text: str,
    *,
    enable_semantic: bool = False,
) -> dict[str, Any]:
    """Return blended ATS score + detail for storage/UI.

    ``enable_semantic`` is accepted for env compatibility but ignored on free tier
    (no MiniLM/torch). Overall = 35% structure + 65% keywords.
    """
    _ = enable_semantic  # reserved for paid-tier worker
    structure = _structure_score(resume_text)
    skills = extract_skills_from_jd(jd_text)
    keywords = _keyword_score(resume_text, skills)
    overall = round(
        structure["score"] * STRUCTURE_WEIGHT + keywords["score"] * KEYWORD_WEIGHT,
        1,
    )
    return {
        "ats_score": overall,
        "structure_score": structure["score"],
        "keyword_score": keywords["score"],
        "matched_skills": [m["keyword"] for m in keywords["matched"]],
        "missing_skills": keywords["missing"],
        "jd_skills": skills,
        "structure": structure,
        "keywords": keywords,
        "fit_label": (
            "Strong match"
            if overall >= 75
            else "Moderate match"
            if overall >= 50
            else "Weak match"
        ),
        "semantic_enabled": False,
    }
