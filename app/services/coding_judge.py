"""SandboxAPI (RapidAPI free) client for sandboxed coding test execution.

Never executes candidate code on the interview host.
Perl is accepted in question metadata but is not executable on the free SandboxAPI plan.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("app.services.coding_judge")

# Languages shown in recruiter/candidate UI
SUPPORTED_CODING_LANGUAGES = ("c", "cpp", "python", "perl", "java", "javascript")

# Languages SandboxAPI free tier can actually run
EXECUTABLE_CODING_LANGUAGES = ("c", "cpp", "python", "java", "javascript")

# SandboxAPI language ids
SANDBOXAPI_LANGUAGE_IDS: dict[str, str] = {
    "c": "c",
    "cpp": "cpp",
    "python": "python3",
    "java": "java",
    "javascript": "javascript",
}

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
        "# Perl is not executable on the current free judge.\n"
        "# Prefer Python / Java / JavaScript / C / C++ for demos.\n"
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
    """Raised when the remote judge is unavailable or rejects a submission."""

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


def sandboxapi_language_id(language: str) -> str:
    normalized = normalize_coding_language(language)
    if not normalized:
        raise CodingJudgeError(f"Unsupported language: {language}", retryable=False)
    if normalized not in EXECUTABLE_CODING_LANGUAGES:
        raise CodingJudgeError(
            f"{normalized} is not executable on the free SandboxAPI judge. "
            "Use C, C++, Python, Java, or JavaScript.",
            retryable=False,
        )
    return SANDBOXAPI_LANGUAGE_IDS[normalized]


def _normalize_stdout(value: str | None) -> str:
    text = value or ""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _rapidapi_key() -> str:
    return (
        settings.CODING_RAPIDAPI_KEY.strip()
        or settings.JUDGE0_RAPIDAPI_KEY.strip()
    )


def coding_judge_configured() -> bool:
    return bool(settings.CODING_QUESTIONS_ENABLED and _rapidapi_key())


def _headers() -> dict[str, str]:
    host = (
        settings.CODING_JUDGE_HOST.strip()
        or settings.JUDGE0_RAPIDAPI_HOST.strip()
        or "sandboxapi.p.rapidapi.com"
    )
    return {
        "Content-Type": "application/json",
        "X-RapidAPI-Key": _rapidapi_key(),
        "X-RapidAPI-Host": host,
    }


def _base_url() -> str:
    host = (
        settings.CODING_JUDGE_HOST.strip()
        or settings.JUDGE0_RAPIDAPI_HOST.strip()
        or "sandboxapi.p.rapidapi.com"
    )
    return f"https://{host}"


def _execute_once(
    client: httpx.Client,
    *,
    source: str,
    language_id: str,
    stdin: str,
    timeout_sec: int,
) -> dict[str, Any]:
    payload = {
        "language": language_id,
        "code": source,
        "stdin": stdin if stdin is not None else "",
        "timeout": timeout_sec,
    }
    url = f"{_base_url()}/v1/execute"
    try:
        response = client.post(
            url,
            headers=_headers(),
            json=payload,
            timeout=max(45.0, float(timeout_sec) + 25.0),
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
            "Judge temporarily unavailable — free monthly quota reached. Try again later."
        )
    if response.status_code == 401 or response.status_code == 403:
        logger.warning("SandboxAPI auth error %s: %s", response.status_code, response.text[:200])
        raise CodingJudgeError(
            "Judge auth failed — subscribe to SandboxAPI Basic (Free) on RapidAPI and check the key.",
            retryable=False,
        )

    data: dict[str, Any] | None = None
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        data = None

    # SandboxAPI often returns HTTP 408 for execution timeouts (and sometimes
    # compile/runtime failures) WITH a normal result body. Treat those as
    # case results, not judge outages.
    if data is not None and (
        response.status_code < 400
        or response.status_code == 408
        or "status" in data
        or "stdout" in data
        or "stderr" in data
    ):
        if response.status_code >= 400 and response.status_code != 408:
            logger.info(
                "SandboxAPI HTTP %s with execution payload status=%s",
                response.status_code,
                data.get("status"),
            )
        return data

    if response.status_code >= 400:
        detail = response.text[:300]
        logger.warning("SandboxAPI error %s: %s", response.status_code, detail)
        raise CodingJudgeError("Judge temporarily unavailable — try again.")

    raise CodingJudgeError("Judge returned an unexpected response.")


def run_test_cases(
    *,
    source: str,
    language: str,
    tests: list[dict[str, Any]],
    time_limit_ms: int | None = None,
    memory_limit_mb: int | None = None,
) -> RunSummary:
    """Execute source against stdin/expected_stdout pairs via SandboxAPI."""
    del memory_limit_mb  # SandboxAPI free plan uses its own memory caps
    if not coding_judge_configured():
        raise CodingJudgeError(
            "Coding judge is not configured. Set CODING_RAPIDAPI_KEY (or JUDGE0_RAPIDAPI_KEY) "
            "and CODING_QUESTIONS_ENABLED.",
            retryable=False,
        )
    if not source or not str(source).strip():
        raise CodingJudgeError("Source code is empty.", retryable=False)
    if not tests:
        return RunSummary(passed=0, total=0, error="No test cases provided.")

    language_id = sandboxapi_language_id(language)
    # Free SandboxAPI needs headroom for compile (esp. C/C++/Java). Floor at 5s.
    timeout_sec = max(5, min(int((time_limit_ms or 5000) / 1000) or 5, 30))

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
                result = _execute_once(
                    client,
                    source=source,
                    language_id=language_id,
                    stdin=stdin,
                    timeout_sec=timeout_sec,
                )
            except CodingJudgeError as exc:
                case.status = "judge_error"
                case.stderr = str(exc)
                summary.cases.append(case)
                summary.error = str(exc)
                break

            status = str(result.get("status") or "")
            actual = _normalize_stdout(result.get("stdout"))
            expected_norm = _normalize_stdout(expected)
            # Some SandboxAPI plans also set expected_output comparison server-side
            if result.get("expected_output") is not None and status == "wrong_answer":
                actual = _normalize_stdout(result.get("stdout"))

            case.actual_stdout = actual
            case.status = status or ("Accepted" if actual == expected_norm else "Wrong Answer")
            case.stderr = str(result.get("stderr") or result.get("compile_output") or "")[:500]
            if result.get("execution_time_ms") is not None:
                case.time = str(result.get("execution_time_ms"))
            try:
                case.memory = (
                    int(result["memory_used_kb"])
                    if result.get("memory_used_kb") is not None
                    else None
                )
            except (TypeError, ValueError):
                case.memory = None

            exit_code = result.get("exit_code")
            status_l = status.lower()
            timed_out = status_l in ("timeout", "time_limit_exceeded") or response_is_timeout(
                status_l, exit_code
            )
            compile_fail = status_l in ("compile_error", "compilation_error") or (
                bool(case.stderr)
                and "error:" in case.stderr.lower()
                and actual == ""
                and exit_code not in (0, None)
            )
            ok_status = status_l in ("", "completed", "accepted", "ok", "success")
            if timed_out:
                case.status = "Time Limit Exceeded"
                case.passed = False
            elif compile_fail:
                case.status = "Compilation Error"
                case.passed = False
            elif ok_status and (exit_code in (None, 0)) and actual == expected_norm:
                case.passed = True
                case.status = "Accepted"
                summary.passed += 1
            elif actual != expected_norm and ok_status and exit_code in (None, 0):
                case.status = "Wrong Answer"
            elif exit_code not in (None, 0) and not ok_status:
                case.status = status or "Runtime Error"
            summary.cases.append(case)
            time.sleep(0.1)

    return summary


def response_is_timeout(status_l: str, exit_code: Any) -> bool:
    return status_l == "timeout" or (exit_code == -1 and status_l in ("", "timeout"))


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
