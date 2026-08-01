"""Unit tests for coding judge helpers (mocked HTTP — SandboxAPI)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.coding_judge import (
    judgment_from_run_summary,
    normalize_coding_language,
    public_run_payload,
    run_test_cases,
    CodingJudgeError,
    RunSummary,
    CaseResult,
    sandboxapi_language_id,
)


def test_normalize_coding_language_aliases():
    assert normalize_coding_language("Python3") == "python"
    assert normalize_coding_language("c++") == "cpp"
    assert normalize_coding_language("js") == "javascript"
    assert normalize_coding_language("fortran") is None


def test_perl_not_executable():
    with pytest.raises(CodingJudgeError):
        sandboxapi_language_id("perl")


def test_judgment_from_run_summary_scores():
    summary = RunSummary(
        passed=2,
        total=4,
        cases=[
            CaseResult("1", "1", "1", True, "Accepted"),
            CaseResult("2", "2", "2", True, "Accepted"),
            CaseResult("3", "3", "9", False, "Wrong Answer"),
            CaseResult("4", "4", "", False, "Runtime Error"),
        ],
    )
    judgment = judgment_from_run_summary(summary, marks=20)
    assert judgment["weighted_total"] == 50.0
    assert judgment["grading_mode"] == "coding_judge"
    assert judgment["run_summary"]["passed"] == 2
    assert judgment["run_summary"]["total"] == 4


def test_public_run_payload_includes_io():
    summary = RunSummary(
        passed=1,
        total=1,
        cases=[CaseResult("a\n", "b", "b", True, "Accepted")],
    )
    payload = public_run_payload(summary)
    assert payload["cases"][0]["stdin"] == "a\n"
    assert payload["cases"][0]["expected_stdout"] == "b"


@patch("app.services.coding_judge.coding_judge_configured", return_value=True)
@patch("app.services.coding_judge.httpx.Client")
def test_run_test_cases_compares_stdout(mock_client_cls, _configured):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "status": "completed",
        "stdout": "6\n",
        "stderr": "",
        "exit_code": 0,
        "execution_time_ms": 12,
        "memory_used_kb": 1024,
    }
    client.post.return_value = response

    summary = run_test_cases(
        source="print(6)",
        language="python",
        tests=[{"stdin": "", "expected_stdout": "6"}],
    )
    assert summary.passed == 1
    assert summary.total == 1
    assert summary.cases[0].passed is True


@patch("app.services.coding_judge.coding_judge_configured", return_value=True)
@patch("app.services.coding_judge.httpx.Client")
def test_run_test_cases_treats_http_408_as_case_result(mock_client_cls, _configured):
    """SandboxAPI returns HTTP 408 with a body for TLE / some failures — not an outage."""
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    response = MagicMock()
    response.status_code = 408
    response.json.return_value = {
        "status": "timeout",
        "stdout": "",
        "stderr": "error: compile failed",
        "exit_code": -1,
        "execution_time_ms": 2100,
    }
    response.text = '{"status":"timeout"}'
    client.post.return_value = response

    summary = run_test_cases(
        source="int main(){while(1){}}",
        language="cpp",
        tests=[{"stdin": "", "expected_stdout": "1"}],
    )
    assert summary.total == 1
    assert summary.passed == 0
    assert summary.error is None
    assert summary.cases[0].status in ("Time Limit Exceeded", "Compilation Error")


@patch("app.services.coding_judge.coding_judge_configured", return_value=False)
def test_run_requires_config(_configured):
    with pytest.raises(CodingJudgeError):
        run_test_cases(
            source="print(1)",
            language="python",
            tests=[{"stdin": "", "expected_stdout": "1"}],
        )
