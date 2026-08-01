"""Coding judge — SandboxAPI (RapidAPI) and/or Piston backends.

Never executes candidate code on the interview host.
Prefer lightweight Piston (public EMKC or self-hosted) when RapidAPI quota/auth
fails; keep SandboxAPI when a free RapidAPI key is configured.

Perl is accepted in question metadata but is not executable on free backends.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from app.core.config import settings

logger = logging.getLogger("app.services.coding_judge")

JudgeBackend = Literal["sandboxapi", "piston"]

# Languages shown in recruiter/candidate UI
SUPPORTED_CODING_LANGUAGES = ("c", "cpp", "python", "perl", "java", "javascript")

# Languages free backends can actually run
EXECUTABLE_CODING_LANGUAGES = ("c", "cpp", "python", "java", "javascript")

SANDBOXAPI_LANGUAGE_IDS: dict[str, str] = {
    "c": "c",
    "cpp": "cpp",
    "python": "python3",
    "java": "java",
    "javascript": "javascript",
}

# Piston language names (version resolved as "*")
PISTON_LANGUAGE_IDS: dict[str, str] = {
    "c": "c",
    "cpp": "c++",
    "python": "python",
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

DEFAULT_PUBLIC_PISTON_URL = "https://emkc.org/api/v2/piston"


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
            f"{normalized} is not executable on the free coding judge. "
            "Use C, C++, Python, Java, or JavaScript.",
            retryable=False,
        )
    return SANDBOXAPI_LANGUAGE_IDS[normalized]


def piston_language_id(language: str) -> str:
    normalized = normalize_coding_language(language)
    if not normalized:
        raise CodingJudgeError(f"Unsupported language: {language}", retryable=False)
    if normalized not in EXECUTABLE_CODING_LANGUAGES:
        raise CodingJudgeError(
            f"{normalized} is not executable on the free coding judge. "
            "Use C, C++, Python, Java, or JavaScript.",
            retryable=False,
        )
    return PISTON_LANGUAGE_IDS[normalized]


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


def _piston_base_url() -> str:
    configured = (settings.CODING_PISTON_URL or "").strip().rstrip("/")
    if configured:
        return configured
    return DEFAULT_PUBLIC_PISTON_URL


def sandboxapi_available() -> bool:
    return bool(_rapidapi_key())


def piston_available() -> bool:
    # Public EMKC Piston is always reachable as a free fallback when enabled.
    backend = (settings.CODING_JUDGE_BACKEND or "auto").strip().lower()
    if backend == "sandboxapi":
        return False
    if backend == "piston":
        return True
    # auto
    return True


def coding_judge_configured() -> bool:
    if not settings.CODING_QUESTIONS_ENABLED:
        return False
    backend = (settings.CODING_JUDGE_BACKEND or "auto").strip().lower()
    if backend == "sandboxapi":
        return sandboxapi_available()
    if backend == "piston":
        return piston_available()
    # auto: either RapidAPI key or Piston (public/self-hosted)
    return sandboxapi_available() or piston_available()


def active_judge_backends() -> list[JudgeBackend]:
    """Ordered backends to try for this process."""
    backend = (settings.CODING_JUDGE_BACKEND or "auto").strip().lower()
    if backend == "sandboxapi":
        return ["sandboxapi"] if sandboxapi_available() else []
    if backend == "piston":
        return ["piston"] if piston_available() else []
    # Prefer SandboxAPI when keyed (stable for demos), then Piston fallback.
    ordered: list[JudgeBackend] = []
    if sandboxapi_available():
        ordered.append("sandboxapi")
    if piston_available():
        ordered.append("piston")
    return ordered


def _sandbox_headers() -> dict[str, str]:
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


def _sandbox_base_url() -> str:
    host = (
        settings.CODING_JUDGE_HOST.strip()
        or settings.JUDGE0_RAPIDAPI_HOST.strip()
        or "sandboxapi.p.rapidapi.com"
    )
    return f"https://{host}"


def _execute_sandboxapi(
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
    url = f"{_sandbox_base_url()}/v1/execute"
    try:
        response = client.post(
            url,
            headers=_sandbox_headers(),
            json=payload,
            timeout=max(45.0, float(timeout_sec) + 25.0),
        )
    except httpx.TimeoutException as exc:
        raise CodingJudgeError(
            "Judge temporarily unavailable — try again (timeout)."
        ) from exc
    except httpx.HTTPError as exc:
        raise CodingJudgeError("Judge temporarily unavailable — try again.") from exc

    if response.status_code == 429:
        raise CodingJudgeError(
            "Judge temporarily unavailable — free monthly quota reached. Try again later."
        )
    if response.status_code in (401, 403):
        logger.warning(
            "SandboxAPI auth error %s: %s", response.status_code, response.text[:200]
        )
        raise CodingJudgeError(
            "Judge auth failed — check CODING_RAPIDAPI_KEY or switch to Piston "
            "(CODING_JUDGE_BACKEND=piston).",
            retryable=False,
        )

    data: dict[str, Any] | None = None
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        data = None

    if data is not None and (
        response.status_code < 400
        or response.status_code == 408
        or "status" in data
        or "stdout" in data
        or "stderr" in data
    ):
        return data

    if response.status_code >= 400:
        logger.warning("SandboxAPI error %s: %s", response.status_code, response.text[:300])
        raise CodingJudgeError("Judge temporarily unavailable — try again.")

    raise CodingJudgeError("Judge returned an unexpected response.")


def _execute_piston(
    client: httpx.Client,
    *,
    source: str,
    language: str,
    stdin: str,
    timeout_sec: int,
) -> dict[str, Any]:
    """Normalize Piston execute response into SandboxAPI-like shape."""
    lang = piston_language_id(language)
    url = f"{_piston_base_url()}/execute"
    payload = {
        "language": lang,
        "version": "*",
        "files": [{"content": source}],
        "stdin": stdin if stdin is not None else "",
        "run_timeout": max(1000, min(timeout_sec * 1000, 30000)),
    }
    try:
        response = client.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=max(45.0, float(timeout_sec) + 25.0),
        )
    except httpx.TimeoutException as exc:
        raise CodingJudgeError(
            "Piston judge timeout — try again."
        ) from exc
    except httpx.HTTPError as exc:
        raise CodingJudgeError("Piston judge unavailable — try again.") from exc

    if response.status_code == 429:
        raise CodingJudgeError(
            "Piston rate limit hit — wait a moment or self-host Piston on EC2."
        )
    if response.status_code >= 400:
        logger.warning("Piston error %s: %s", response.status_code, response.text[:300])
        raise CodingJudgeError("Piston judge temporarily unavailable — try again.")

    try:
        data = response.json()
    except Exception as exc:
        raise CodingJudgeError("Piston returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise CodingJudgeError("Piston returned unexpected response.")

    compile_block = data.get("compile") if isinstance(data.get("compile"), dict) else {}
    run_block = data.get("run") if isinstance(data.get("run"), dict) else {}
    compile_code = compile_block.get("code")
    run_code = run_block.get("code")
    stdout = str(run_block.get("stdout") or "")
    stderr_parts = [
        str(compile_block.get("stderr") or ""),
        str(run_block.get("stderr") or ""),
        str(run_block.get("output") or "") if not stdout else "",
    ]
    stderr = "\n".join(p for p in stderr_parts if p).strip()

    if compile_code not in (None, 0):
        status = "compile_error"
        exit_code = compile_code
    elif run_code == -1 or str(run_block.get("signal") or "").upper() in (
        "SIGKILL",
        "SIGXCPU",
    ):
        status = "timeout"
        exit_code = -1
    elif run_code not in (None, 0):
        status = "runtime_error"
        exit_code = run_code
    else:
        status = "completed"
        exit_code = 0

    return {
        "status": status,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "execution_time_ms": run_block.get("cpu_time"),
        "memory_used_kb": None,
    }


# Back-compat alias used by older unit tests
def _execute_once(
    client: httpx.Client,
    *,
    source: str,
    language_id: str,
    stdin: str,
    timeout_sec: int,
) -> dict[str, Any]:
    return _execute_sandboxapi(
        client,
        source=source,
        language_id=language_id,
        stdin=stdin,
        timeout_sec=timeout_sec,
    )


def _grade_case_from_result(
    result: dict[str, Any],
    *,
    expected: str,
) -> CaseResult:
    stdin = ""  # filled by caller
    case = CaseResult(stdin=stdin, expected_stdout=expected)
    status = str(result.get("status") or "")
    actual = _normalize_stdout(result.get("stdout"))
    expected_norm = _normalize_stdout(expected)
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
    elif actual != expected_norm and ok_status and exit_code in (None, 0):
        case.status = "Wrong Answer"
        case.passed = False
    elif exit_code not in (None, 0) and not ok_status:
        case.status = status or "Runtime Error"
        case.passed = False
    return case


def _run_with_backend(
    backend: JudgeBackend,
    *,
    source: str,
    language: str,
    tests: list[dict[str, Any]],
    timeout_sec: int,
) -> RunSummary:
    summary = RunSummary(total=len(tests))
    with httpx.Client() as client:
        for raw in tests:
            stdin = str(raw.get("stdin", raw.get("input", "")) or "")
            expected = str(
                raw.get("expected_stdout", raw.get("expected", raw.get("output", "")))
                or ""
            )
            try:
                if backend == "sandboxapi":
                    result = _execute_sandboxapi(
                        client,
                        source=source,
                        language_id=sandboxapi_language_id(language),
                        stdin=stdin,
                        timeout_sec=timeout_sec,
                    )
                else:
                    result = _execute_piston(
                        client,
                        source=source,
                        language=language,
                        stdin=stdin,
                        timeout_sec=timeout_sec,
                    )
            except CodingJudgeError as exc:
                case = CaseResult(stdin=stdin, expected_stdout=expected)
                case.status = "judge_error"
                case.stderr = str(exc)
                summary.cases.append(case)
                summary.error = str(exc)
                break

            case = _grade_case_from_result(result, expected=expected)
            case.stdin = stdin
            if case.passed:
                summary.passed += 1
            summary.cases.append(case)
            time.sleep(0.05)
    return summary


def run_test_cases(
    *,
    source: str,
    language: str,
    tests: list[dict[str, Any]],
    time_limit_ms: int | None = None,
    memory_limit_mb: int | None = None,
) -> RunSummary:
    """Execute source against stdin/expected_stdout pairs via configured backends."""
    del memory_limit_mb  # free backends use their own memory caps
    if not coding_judge_configured():
        raise CodingJudgeError(
            "Coding judge is not configured. Set CODING_RAPIDAPI_KEY and/or "
            "CODING_PISTON_URL (or CODING_JUDGE_BACKEND=piston for public EMKC), "
            "and CODING_QUESTIONS_ENABLED=true.",
            retryable=False,
        )
    if not source or not str(source).strip():
        raise CodingJudgeError("Source code is empty.", retryable=False)
    if not tests:
        return RunSummary(passed=0, total=0, error="No test cases provided.")

    # Validate language early
    sandboxapi_language_id(language)
    timeout_sec = max(5, min(int((time_limit_ms or 5000) / 1000) or 5, 30))
    backends = active_judge_backends()
    if not backends:
        raise CodingJudgeError(
            "No coding judge backend available.",
            retryable=False,
        )

    last_error: str | None = None
    for idx, backend in enumerate(backends):
        logger.info("Coding judge using backend=%s", backend)
        summary = _run_with_backend(
            backend,
            source=source,
            language=language,
            tests=tests,
            timeout_sec=timeout_sec,
        )
        # Fall through to next backend on transport/quota/auth outages only.
        if summary.error and idx + 1 < len(backends):
            err_l = summary.error.lower()
            retryable_outage = any(
                tip in err_l
                for tip in (
                    "quota",
                    "auth failed",
                    "temporarily unavailable",
                    "rate limit",
                    "timeout",
                    "unavailable",
                )
            )
            if retryable_outage:
                last_error = summary.error
                logger.warning(
                    "Backend %s failed (%s); trying fallback", backend, summary.error
                )
                continue
        return summary

    return RunSummary(
        passed=0,
        total=len(tests),
        error=last_error or "All coding judge backends failed.",
    )


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
