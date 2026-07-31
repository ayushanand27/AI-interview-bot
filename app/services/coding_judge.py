"""Judge0 CE (RapidAPI) client for sandboxed coding test execution.

Never executes candidate code on the interview host — all runs go through Judge0.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("app.services.coding_judge")

# Judge0 CE language IDs (https://ce.judge0.com)
CODING_LANGUAGES: dict[str, int] = {
    "c": 50,
    "cpp": 54,
    "c++": 54,
    "java": 62,
    "javascript": 63,
    "js": 63,
    "python": 71,
    "python3": 71,
    "perl": 85,
}

SUPPORTED_CODING_LANGUAGES = ("c", "cpp", "python", "perl", "java", "javascript")

LANGUAGE_EXTENSIONS: dict[str, str] = {
    "c": "c",
    "cpp": "cpp",
    "python": "py",
    "perl": "pl",
    "java": "java",
    "javascript": "js",
}

LANGUAGE_STARTERS: dict[str, str] = {
    "c": (
        "#include <stdio.h>\n\n"
        "int main(void) {\n"
        "    /* Read from stdin, write to stdout */\n"
        "    return 0;\n"
        "}\n"
    ),
    "cpp": (
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n\n"
        "int main() {\n"
        "    ios::sync_with_stdio(false);\n"
        "    cin.tie(nullptr);\n"
        "    // Read from stdin, write to stdout\n"
        "    return 0;\n"
        "}\n"
    ),
    "python": (
        "# Read from stdin, write to stdout\n"
        "def solve():\n"
        "    pass\n\n"
        "if __name__ == '__main__':\n"
        "    solve()\n"
    ),
    "perl": (
        "#!/usr/bin/perl\n"
        "use strict;\n"
        "use warnings;\n\n"
        "# Read from STDIN, write to STDOUT\n"
    ),
    "java": (
        "import java.util.*;\n\n"
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        Scanner sc = new Scanner(System.in);\n"
        "        // Read from stdin, write to stdout\n"
        "    }\n"
        "}\n"
    ),
    "javascript": (
        "const fs = require('fs');\n"
        "const input = fs.readFileSync(0, 'utf8').trim();\n"
        "// Read from stdin, write to stdout\n"
        "console.log(input);\n"
    ),
}


class CodingJudgeError(Exception):
    """Raised when Judge0 is unavailable or rejects a submission."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class CaseResult:
    stdin: str
    expected_stdout: str
    actual_stdout: str = ""
    passed: bool = False
    status: str = ""
    stderr: str = ""
    time: str | None = None
    memory: int | None = None


@dataclass
class RunSummary:
    passed: int = 0
    total: int = 0
    cases: list[CaseResult] = field(default_factory=list)
    error: str | None = None

    @property
    def score_percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return round(100.0 * self.passed / self.total, 2)


def normalize_coding_language(raw: str | None) -> str | None:
    if not raw:
        return None
    key = str(raw).strip().lower()
    aliases = {
        "c++": "cpp",
        "py": "python",
        "python3": "python",
        "js": "javascript",
        "node": "javascript",
        "nodejs": "javascript",
    }
    key = aliases.get(key, key)
    if key in SUPPORTED_CODING_LANGUAGES:
        return key
    return None


def judge0_language_id(language: str) -> int:
    normalized = normalize_coding_language(language)
    if not normalized:
        raise CodingJudgeError(f"Unsupported language: {language}", retryable=False)
    return CODING_LANGUAGES[normalized]


def _normalize_stdout(value: str | None) -> str:
    text = value or ""
    # Judge0 often appends a trailing newline; compare line-trimmed.
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def coding_judge_configured() -> bool:
    return bool(
        settings.CODING_QUESTIONS_ENABLED
        and settings.JUDGE0_RAPIDAPI_KEY.strip()
    )


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-RapidAPI-Key": settings.JUDGE0_RAPIDAPI_KEY.strip(),
        "X-RapidAPI-Host": settings.JUDGE0_RAPIDAPI_HOST.strip(),
    }


def _base_url() -> str:
    host = settings.JUDGE0_RAPIDAPI_HOST.strip() or "judge0-ce.p.rapidapi.com"
    return f"https://{host}"


def _create_submission(
    client: httpx.Client,
    *,
    source: str,
    language_id: int,
    stdin: str,
    cpu_time_limit: float,
    memory_limit_kb: int,
) -> dict[str, Any]:
    payload = {
        "source_code": source,
        "language_id": language_id,
        "stdin": stdin if stdin is not None else "",
        "cpu_time_limit": cpu_time_limit,
        "wall_time_limit": max(cpu_time_limit * 2, 5.0),
        "memory_limit": memory_limit_kb,
    }
    url = f"{_base_url()}/submissions"
    try:
        response = client.post(
            url,
            params={"base64_encoded": "false", "wait": "true"},
            headers=_headers(),
            json=payload,
            timeout=max(30.0, cpu_time_limit + 25.0),
        )
    except httpx.TimeoutException as exc:
        raise CodingJudgeError(
            "Judge temporarily unavailable — try again (timeout)."
        ) from exc
    except httpx.HTTPError as exc:
        raise CodingJudgeError(
            "Judge temporarily unavailable — try again."
        ) from exc

    if response.status_code == 429:
        raise CodingJudgeError(
            "Judge temporarily unavailable — daily or concurrency limit reached. Try again shortly."
        )
    if response.status_code >= 400:
        detail = response.text[:300]
        logger.warning("Judge0 error %s: %s", response.status_code, detail)
        raise CodingJudgeError(
            "Judge temporarily unavailable — try again."
        )

    data = response.json()
    if not isinstance(data, dict):
        raise CodingJudgeError("Judge returned an unexpected response.")
    return data


def run_test_cases(
    *,
    source: str,
    language: str,
    tests: list[dict[str, Any]],
    time_limit_ms: int | None = None,
    memory_limit_mb: int | None = None,
) -> RunSummary:
    """Execute source against stdin/expected_stdout pairs via Judge0."""
    if not coding_judge_configured():
        raise CodingJudgeError(
            "Coding judge is not configured. Set JUDGE0_RAPIDAPI_KEY and CODING_QUESTIONS_ENABLED.",
            retryable=False,
        )
    if not source or not str(source).strip():
        raise CodingJudgeError("Source code is empty.", retryable=False)
    if not tests:
        return RunSummary(passed=0, total=0, error="No test cases provided.")

    language_id = judge0_language_id(language)
    cpu_time = max(0.5, min((time_limit_ms or 2000) / 1000.0, 5.0))
    memory_kb = max(16_000, min((memory_limit_mb or 128) * 1000, 256_000))

    summary = RunSummary(total=len(tests))
    with httpx.Client() as client:
        for raw in tests:
            stdin = str(raw.get("stdin", raw.get("input", "")) or "")
            expected = str(
                raw.get("expected_stdout", raw.get("expected", raw.get("output", "")))
                or ""
            )
            case = CaseResult(stdin=stdin, expected_stdout=expected)
            try:
                result = _create_submission(
                    client,
                    source=source,
                    language_id=language_id,
                    stdin=stdin,
                    cpu_time_limit=cpu_time,
                    memory_limit_kb=memory_kb,
                )
            except CodingJudgeError as exc:
                case.status = "judge_error"
                case.stderr = str(exc)
                summary.cases.append(case)
                summary.error = str(exc)
                # Stop early on judge outage so demos fail fast.
                break

            status_obj = result.get("status") or {}
            status_desc = (
                status_obj.get("description")
                if isinstance(status_obj, dict)
                else str(status_obj or "")
            )
            actual = _normalize_stdout(result.get("stdout"))
            expected_norm = _normalize_stdout(expected)
            case.actual_stdout = actual
            case.status = str(status_desc or "")
            case.stderr = str(result.get("stderr") or result.get("compile_output") or "")[:500]
            case.time = str(result.get("time")) if result.get("time") is not None else None
            try:
                case.memory = int(result["memory"]) if result.get("memory") is not None else None
            except (TypeError, ValueError):
                case.memory = None

            status_id = status_obj.get("id") if isinstance(status_obj, dict) else None
            # 3 = Accepted
            if status_id == 3 and actual == expected_norm:
                case.passed = True
                summary.passed += 1
            elif status_id == 3 and actual != expected_norm:
                case.status = "Wrong Answer"
            summary.cases.append(case)
            # Small pause to respect free-tier concurrency=1
            time.sleep(0.15)

    return summary


def judgment_from_run_summary(summary: RunSummary, *, marks: float) -> dict[str, Any]:
    """Map a RunSummary into the existing answer_judgments shape."""
    score = summary.score_percent
    if summary.total <= 0:
        reasoning = summary.error or "No hidden test cases were configured."
        return {
            "weighted_total": 0.0,
            "overall_reasoning": reasoning,
            "strengths": [],
            "improvements": ["Add hidden test cases to grade coding answers."],
            "criteria_scores": {
                "coding_tests": {"score": 0.0, "reasoning": reasoning}
            },
            "grading_mode": "coding_judge",
            "is_correct": False,
            "max_marks": float(marks),
            "run_summary": {
                "passed": 0,
                "total": 0,
                "error": summary.error,
                "cases": [],
            },
        }

    reasoning = (
        f"Passed {summary.passed}/{summary.total} hidden test case(s)."
        if not summary.error
        else f"Passed {summary.passed}/{summary.total} before judge error: {summary.error}"
    )
    case_payload = [
        {
            "passed": c.passed,
            "status": c.status,
            "stdin_preview": (c.stdin[:120] + "…") if len(c.stdin) > 120 else c.stdin,
            "stderr_preview": (c.stderr[:200] + "…") if len(c.stderr) > 200 else c.stderr,
        }
        for c in summary.cases
    ]
    return {
        "weighted_total": score,
        "overall_reasoning": reasoning,
        "strengths": [f"Passed {summary.passed} test(s)"] if summary.passed else [],
        "improvements": []
        if summary.passed == summary.total
        else ["Review failing cases; check edge cases and I/O format."],
        "criteria_scores": {
            "coding_tests": {"score": score, "reasoning": reasoning}
        },
        "grading_mode": "coding_judge",
        "is_correct": summary.passed == summary.total and summary.total > 0,
        "max_marks": float(marks),
        "run_summary": {
            "passed": summary.passed,
            "total": summary.total,
            "error": summary.error,
            "cases": case_payload,
        },
    }


def public_run_payload(summary: RunSummary) -> dict[str, Any]:
    """Candidate-visible public-test results (includes expected/actual for public cases)."""
    return {
        "passed": summary.passed,
        "total": summary.total,
        "error": summary.error,
        "cases": [
            {
                "passed": c.passed,
                "status": c.status,
                "stdin": c.stdin,
                "expected_stdout": c.expected_stdout,
                "actual_stdout": c.actual_stdout,
                "stderr": c.stderr[:300] if c.stderr else "",
            }
            for c in summary.cases
        ],
    }
