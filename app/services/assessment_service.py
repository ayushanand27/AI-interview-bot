"""Recruiter assessment creation — JD-only question generation via Groq."""

from __future__ import annotations

import json
import random
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AIException, ConflictException, NotFoundException
from app.db.interview_invite_model import InterviewInvite
from app.schemas.recruiter_assessment import (
    AssessmentQuestion,
    AssessmentSummary,
    CreateAssessmentRequest,
    CreateAssessmentResponse,
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    SendAssessmentInvitesRequest,
    SendAssessmentInvitesResponse,
    UpdateAssessmentRequest,
)
from app.services.email_service import send_assessment_invite_email, smtp_delivery_hint
from app.services.groq_client import groq_chat_completion
from app.services.question_utils import (
    QUESTION_TYPES,
    default_time_seconds,
    normalize_question,
    normalize_questions,
    question_text,
)


def _unique_bank_picker(bank: list):
    """Yield bank items shuffled without replacement; reshuffle when exhausted."""
    order = list(range(len(bank)))
    random.shuffle(order)
    idx = 0

    def next_item():
        nonlocal idx, order
        if not bank:
            raise ValueError("empty bank")
        if idx >= len(order):
            order = list(range(len(bank)))
            random.shuffle(order)
            idx = 0
        item = bank[order[idx]]
        idx += 1
        return item

    return next_item


def _as_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _strip_markdown_code_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def _distribute_types(question_count: int, types: list[str]) -> list[str]:
    if not types:
        types = ["subjective"]
    cleaned = [t for t in types if t in QUESTION_TYPES]
    if not cleaned:
        cleaned = ["subjective"]
    out: list[str] = []
    for i in range(question_count):
        out.append(cleaned[i % len(cleaned)])
    return out


def _fallback_question_dicts(
    jd_text: str,
    question_count: int,
    difficulty: str,
    question_types: list[str] | None,
) -> list[dict]:
    role_hint = jd_text.strip().splitlines()[0][:120] if jd_text.strip() else "this role"
    type_plan = _distribute_types(question_count, question_types or ["subjective"])
    subjective_bank = [
        f"Based on the job description for {role_hint}, what relevant experience do you bring to this {difficulty.lower()} position?",
        "Describe a project where you applied skills mentioned in the job description. What was your contribution?",
        "How do you approach learning new tools or frameworks required for a role like this?",
        "Walk me through how you debug and resolve a production issue under time pressure.",
        "Tell me about a time you collaborated with others to deliver a feature end to end.",
        "Describe a technical decision you made, the tradeoffs you considered, and the outcome.",
        "How do you prioritize tasks when multiple stakeholders have competing deadlines?",
        "Explain a complex technical concept from the job description as you would to a non-technical stakeholder.",
        "Describe how you would design a scalable component related to this role. What bottlenecks would you watch for?",
        "Tell me about a time you disagreed with a technical approach. How did you resolve it?",
        "How do you ensure code quality when shipping under a tight deadline?",
        "Walk through how you would investigate intermittent failures in a distributed system.",
        "Describe your approach to onboarding onto an unfamiliar legacy codebase.",
        "How do you balance technical debt reduction with feature delivery?",
        "Explain a performance optimization you made and how you measured its impact.",
        "Describe how you would handle a sudden production spike for a service in this domain.",
    ]
    mcq_bank = [
        {
            "text": "Which practice best improves long-term code maintainability?",
            "options": [
                "Clear naming and small focused functions",
                "Copy-pasting proven snippets everywhere",
                "Avoiding code reviews to move faster",
                "Keeping all logic in one module",
            ],
            "correct_indices": [0],
        },
        {
            "text": "What is the primary goal of writing automated tests?",
            "options": [
                "Increase deploy confidence and catch regressions early",
                "Replace all manual QA forever",
                "Make the codebase larger on purpose",
                "Slow down every feature release",
            ],
            "correct_indices": [0],
        },
        {
            "text": "In a production incident, what should you do first?",
            "options": [
                "Stabilize impact and communicate status",
                "Rewrite the system from scratch",
                "Ignore metrics and wait",
                "Delete logs to reduce noise",
            ],
            "correct_indices": [0],
        },
        {
            "text": "Which HTTP status best indicates a successful resource creation?",
            "options": ["201 Created", "204 No Content", "301 Moved Permanently", "409 Conflict"],
            "correct_indices": [0],
        },
        {
            "text": "What does CAP theorem say a distributed system cannot guarantee simultaneously?",
            "options": [
                "Consistency, Availability, and Partition tolerance",
                "Caching, Auth, and Pagination",
                "CPU, Memory, and Disk",
                "Latency, Throughput, and Cost",
            ],
            "correct_indices": [0],
        },
        {
            "text": "Which index type is typically best for equality lookups on a high-cardinality column?",
            "options": ["B-tree / hash index", "Full table scan only", "Bitmap on unique UUID", "No index needed"],
            "correct_indices": [0],
        },
        {
            "text": "What is the main benefit of idempotent API design?",
            "options": [
                "Safe retries without unintended duplicate side effects",
                "Faster JSON parsing",
                "Smaller Docker images",
                "Automatic schema migrations",
            ],
            "correct_indices": [0],
        },
        {
            "text": "Which approach best prevents secret leakage in CI/CD?",
            "options": [
                "Store secrets in a vault / secret manager, inject at runtime",
                "Commit .env files for convenience",
                "Put secrets in public README examples",
                "Hard-code keys in frontend bundles",
            ],
            "correct_indices": [0],
        },
    ]
    msq_bank = [
        {
            "text": "Which of the following improve API reliability? Select all that apply.",
            "options": [
                "Timeouts and retries with backoff",
                "Input validation",
                "Hard-coding secrets in source",
                "Health checks and monitoring",
            ],
            "correct_indices": [0, 1, 3],
        },
        {
            "text": "Which practices support secure software delivery? Select all that apply.",
            "options": [
                "Least-privilege access",
                "Dependency vulnerability scanning",
                "Sharing production credentials in chat",
                "Encrypted secrets storage",
            ],
            "correct_indices": [0, 1, 3],
        },
        {
            "text": "Which techniques help diagnose production performance issues? Select all that apply.",
            "options": [
                "Profiling hot paths",
                "Checking slow-query logs",
                "Ignoring p99 latency",
                "Load testing representative traffic",
            ],
            "correct_indices": [0, 1, 3],
        },
        {
            "text": "Which are valid reasons to choose a message queue? Select all that apply.",
            "options": [
                "Decouple producers and consumers",
                "Absorb traffic spikes",
                "Guarantee UI pixel-perfect rendering",
                "Enable asynchronous processing",
            ],
            "correct_indices": [0, 1, 3],
        },
    ]
    numerical_bank = [
        {
            "text": "A service handles 120 requests/minute. How many requests is that per hour?",
            "correct_answer": "7200",
            "tolerance": 0,
        },
        {
            "text": "An API has p95 latency of 0.25 seconds. What is that latency in milliseconds?",
            "correct_answer": "250",
            "tolerance": 0,
        },
        {
            "text": "A team completes 8 story points in a 2-week sprint. What is average points per week?",
            "correct_answer": "4",
            "tolerance": 0,
        },
        {
            "text": "A cache hit rate is 80% of 5000 lookups. How many hits is that?",
            "correct_answer": "4000",
            "tolerance": 0,
        },
        {
            "text": "A binary search on a sorted array of 1,048,576 elements takes at most how many comparisons (log2 N)?",
            "correct_answer": "20",
            "tolerance": 0,
        },
        {
            "text": "If a job runs every 15 minutes, how many runs occur in 24 hours?",
            "correct_answer": "96",
            "tolerance": 0,
        },
    ]

    def _coding(
        text: str,
        public: list[dict],
        hidden: list[dict],
        *,
        starter: str | None = None,
        marks: int = 25,
        time_seconds: int = 1200,
        time_limit_ms: int = 5000,
    ) -> dict:
        return {
            "text": text,
            "languages": ["python", "javascript", "java", "cpp", "c"],
            "starter_code": {
                "python": starter
                or "# Read from stdin, write to stdout\nimport sys\ndata = sys.stdin.read().split()\n"
            },
            "public_tests": public,
            "hidden_tests": hidden,
            "time_seconds": time_seconds,
            "marks": marks,
            "time_limit_ms": time_limit_ms,
            "memory_limit_mb": 128,
        }

    coding_bank = [
        _coding(
            (
                "Two Sum\n"
                "Given an array of integers and a target, return two 0-based indices that sum to target.\n\n"
                "Input:\n"
                "  Line 1: integer N (2 <= N <= 1e5)\n"
                "  Line 2: N integers A[i] (|A[i]| <= 1e9)\n"
                "  Line 3: integer target\n"
                "Output: two indices i j (i < j) with A[i] + A[j] == target. Any valid pair is accepted.\n\n"
                "Example 1:\n"
                "Input:\n4\n2 7 11 15\n9\n"
                "Output:\n0 1\n\n"
                "Example 2:\n"
                "Input:\n3\n3 2 4\n6\n"
                "Output:\n1 2"
            ),
            [
                {"stdin": "4\n2 7 11 15\n9\n", "expected_stdout": "0 1"},
                {"stdin": "3\n3 2 4\n6\n", "expected_stdout": "1 2"},
            ],
            [
                {"stdin": "2\n1 1\n2\n", "expected_stdout": "0 1"},
                {"stdin": "5\n-1 0 5 3 8\n7\n", "expected_stdout": "2 3"},
                {"stdin": "6\n10 20 30 40 50 60\n90\n", "expected_stdout": "2 5"},
            ],
            starter="n = int(input())\narr = list(map(int, input().split()))\ntarget = int(input())\n# print two indices i j\n",
        ),
        _coding(
            (
                "Valid Parentheses\n"
                "Check whether a bracket string is valid.\n\n"
                "Input: one string S of ()[]{} only (1 <= |S| <= 1e5)\n"
                "Output: YES if valid, otherwise NO\n\n"
                "Example 1:\nInput:\n()\nOutput:\nYES\n\n"
                "Example 2:\nInput:\n([)]\nOutput:\nNO"
            ),
            [
                {"stdin": "()\n", "expected_stdout": "YES"},
                {"stdin": "([)]\n", "expected_stdout": "NO"},
                {"stdin": "{[]}\n", "expected_stdout": "YES"},
            ],
            [
                {"stdin": "(((((((((()\n", "expected_stdout": "NO"},
                {"stdin": "([]{})\n", "expected_stdout": "YES"},
                {"stdin": "]\n", "expected_stdout": "NO"},
            ],
            starter="s = input().strip()\n# print YES or NO\n",
            marks=20,
            time_seconds=900,
        ),
        _coding(
            (
                "Longest Substring Without Repeating Characters\n"
                "Find the length of the longest substring with all unique characters.\n\n"
                "Input: string S of lowercase letters (1 <= |S| <= 1e5)\n"
                "Output: a single integer\n\n"
                "Example 1:\nInput:\nabcabcbb\nOutput:\n3\n\n"
                "Example 2:\nInput:\npwwkew\nOutput:\n3"
            ),
            [
                {"stdin": "abcabcbb\n", "expected_stdout": "3"},
                {"stdin": "bbbbb\n", "expected_stdout": "1"},
                {"stdin": "pwwkew\n", "expected_stdout": "3"},
            ],
            [
                {"stdin": "a\n", "expected_stdout": "1"},
                {"stdin": "abcdef\n", "expected_stdout": "6"},
                {"stdin": "abba\n", "expected_stdout": "2"},
            ],
            starter="s = input().strip()\n# print an integer\n",
        ),
        _coding(
            (
                "Maximum Subarray Sum (Kadane)\n"
                "Find the contiguous subarray with the largest sum.\n\n"
                "Input:\n"
                "  Line 1: N (1 <= N <= 1e5)\n"
                "  Line 2: N integers A[i] (|A[i]| <= 1e9)\n"
                "Output: the maximum subarray sum\n\n"
                "Example 1:\nInput:\n9\n-2 1 -3 4 -1 2 1 -5 4\nOutput:\n6\n\n"
                "Example 2:\nInput:\n1\n-3\nOutput:\n-3"
            ),
            [
                {"stdin": "9\n-2 1 -3 4 -1 2 1 -5 4\n", "expected_stdout": "6"},
                {"stdin": "1\n-3\n", "expected_stdout": "-3"},
            ],
            [
                {"stdin": "5\n1 2 3 4 5\n", "expected_stdout": "15"},
                {"stdin": "4\n-1 -2 -3 -4\n", "expected_stdout": "-1"},
                {"stdin": "3\n5 -1 5\n", "expected_stdout": "9"},
            ],
            starter="n = int(input())\narr = list(map(int, input().split()))\n# print max subarray sum\n",
        ),
        _coding(
            (
                "Merge Intervals\n"
                "Merge all overlapping intervals.\n\n"
                "Input:\n"
                "  Line 1: N (1 <= N <= 1e4)\n"
                "  Next N lines: L R (interval inclusive endpoints)\n"
                "Output: merged intervals, one per line as L R, sorted by L\n\n"
                "Example 1:\nInput:\n4\n1 3\n2 6\n8 10\n15 18\nOutput:\n1 6\n8 10\n15 18\n\n"
                "Example 2:\nInput:\n2\n1 4\n4 5\nOutput:\n1 5"
            ),
            [
                {"stdin": "4\n1 3\n2 6\n8 10\n15 18\n", "expected_stdout": "1 6\n8 10\n15 18"},
                {"stdin": "2\n1 4\n4 5\n", "expected_stdout": "1 5"},
            ],
            [
                {"stdin": "1\n5 5\n", "expected_stdout": "5 5"},
                {"stdin": "3\n1 10\n2 3\n4 8\n", "expected_stdout": "1 10"},
                {"stdin": "3\n1 2\n3 4\n5 6\n", "expected_stdout": "1 2\n3 4\n5 6"},
            ],
            starter="n = int(input())\nintervals = [tuple(map(int, input().split())) for _ in range(n)]\n# print merged intervals\n",
            marks=30,
        ),
        _coding(
            (
                "Top K Frequent Elements\n"
                "Return the K most frequent integers (any order).\n\n"
                "Input:\n"
                "  Line 1: N K\n"
                "  Line 2: N integers\n"
                "Output: K integers separated by spaces in ascending order\n\n"
                "Example 1:\nInput:\n6 2\n1 1 1 2 2 3\nOutput:\n1 2\n\n"
                "Example 2:\nInput:\n1 1\n1\nOutput:\n1"
            ),
            [
                {"stdin": "6 2\n1 1 1 2 2 3\n", "expected_stdout": "1 2"},
                {"stdin": "1 1\n1\n", "expected_stdout": "1"},
            ],
            [
                {"stdin": "4 1\n4 4 4 4\n", "expected_stdout": "4"},
                {"stdin": "5 2\n5 5 3 3 1\n", "expected_stdout": "3 5"},
                {"stdin": "3 3\n7 8 9\n", "expected_stdout": "7 8 9"},
            ],
            starter="n, k = map(int, input().split())\narr = list(map(int, input().split()))\n# print k most frequent values\n",
            marks=30,
        ),
        _coding(
            (
                "Product of Array Except Self\n"
                "For each index i, output the product of all elements except A[i]. Do not use division.\n\n"
                "Input:\n"
                "  Line 1: N (2 <= N <= 1e5)\n"
                "  Line 2: N integers A[i] (|A[i]| <= 100)\n"
                "Output: N integers (products) separated by spaces\n\n"
                "Example 1:\nInput:\n4\n1 2 3 4\nOutput:\n24 12 8 6\n\n"
                "Example 2:\nInput:\n5\n-1 1 0 -3 3\nOutput:\n0 0 9 0 0"
            ),
            [
                {"stdin": "4\n1 2 3 4\n", "expected_stdout": "24 12 8 6"},
                {"stdin": "5\n-1 1 0 -3 3\n", "expected_stdout": "0 0 9 0 0"},
            ],
            [
                {"stdin": "2\n2 3\n", "expected_stdout": "3 2"},
                {"stdin": "3\n0 0 2\n", "expected_stdout": "0 0 0"},
                {"stdin": "3\n1 1 1\n", "expected_stdout": "1 1 1"},
            ],
            starter="n = int(input())\narr = list(map(int, input().split()))\n# print n products\n",
            marks=30,
        ),
        _coding(
            (
                "Binary Search First Occurrence\n"
                "Find the first index of target in a sorted array (non-decreasing). Return -1 if missing.\n\n"
                "Input:\n"
                "  Line 1: N target\n"
                "  Line 2: N sorted integers\n"
                "Output: a single index (0-based) or -1\n\n"
                "Example 1:\nInput:\n6 2\n1 2 2 2 3 4\nOutput:\n1\n\n"
                "Example 2:\nInput:\n4 5\n1 2 3 4\nOutput:\n-1"
            ),
            [
                {"stdin": "6 2\n1 2 2 2 3 4\n", "expected_stdout": "1"},
                {"stdin": "4 5\n1 2 3 4\n", "expected_stdout": "-1"},
            ],
            [
                {"stdin": "1 7\n7\n", "expected_stdout": "0"},
                {"stdin": "5 1\n1 1 1 1 1\n", "expected_stdout": "0"},
                {"stdin": "5 9\n1 3 5 7 9\n", "expected_stdout": "4"},
            ],
            starter="n, target = map(int, input().split())\narr = list(map(int, input().split()))\n# print first index or -1\n",
            marks=20,
            time_seconds=900,
        ),
        _coding(
            (
                "Next Greater Element\n"
                "For each element, find the next greater element to its right. Use -1 if none.\n\n"
                "Input:\n"
                "  Line 1: N (1 <= N <= 1e5)\n"
                "  Line 2: N integers\n"
                "Output: N integers separated by spaces\n\n"
                "Example 1:\nInput:\n4\n2 1 2 4\nOutput:\n4 2 4 -1\n\n"
                "Example 2:\nInput:\n3\n3 2 1\nOutput:\n-1 -1 -1"
            ),
            [
                {"stdin": "4\n2 1 2 4\n", "expected_stdout": "4 2 4 -1"},
                {"stdin": "3\n3 2 1\n", "expected_stdout": "-1 -1 -1"},
            ],
            [
                {"stdin": "1\n10\n", "expected_stdout": "-1"},
                {"stdin": "5\n1 2 3 4 5\n", "expected_stdout": "2 3 4 5 -1"},
                {"stdin": "4\n5 4 3 10\n", "expected_stdout": "10 10 10 -1"},
            ],
            starter="n = int(input())\narr = list(map(int, input().split()))\n# print next greater for each index\n",
            marks=30,
        ),
        _coding(
            (
                "Group Anagram Keys Count\n"
                "Count how many distinct anagram groups exist in the list of words.\n\n"
                "Input:\n"
                "  Line 1: N (1 <= N <= 1e4)\n"
                "  Next N lines: lowercase words (length <= 100)\n"
                "Output: number of groups\n\n"
                "Example 1:\nInput:\n6\neat\ntea\ntan\nate\nnat\nbat\nOutput:\n3\n\n"
                "Example 2:\nInput:\n1\na\nOutput:\n1"
            ),
            [
                {"stdin": "6\neat\ntea\ntan\nate\nnat\nbat\n", "expected_stdout": "3"},
                {"stdin": "1\na\n", "expected_stdout": "1"},
            ],
            [
                {"stdin": "3\nabc\nbca\ncab\n", "expected_stdout": "1"},
                {"stdin": "4\nab\nba\ncd\ndc\n", "expected_stdout": "2"},
                {"stdin": "2\nxx\nyy\n", "expected_stdout": "2"},
            ],
            starter="n = int(input())\nwords = [input().strip() for _ in range(n)]\n# print group count\n",
            marks=25,
        ),
        _coding(
            (
                "Rotate Array Right by K\n"
                "Rotate the array to the right by K steps.\n\n"
                "Input:\n"
                "  Line 1: N K\n"
                "  Line 2: N integers\n"
                "Output: rotated array on one line\n\n"
                "Example 1:\nInput:\n7 3\n1 2 3 4 5 6 7\nOutput:\n5 6 7 1 2 3 4\n\n"
                "Example 2:\nInput:\n4 2\n-1 -100 3 99\nOutput:\n3 99 -1 -100"
            ),
            [
                {"stdin": "7 3\n1 2 3 4 5 6 7\n", "expected_stdout": "5 6 7 1 2 3 4"},
                {"stdin": "4 2\n-1 -100 3 99\n", "expected_stdout": "3 99 -1 -100"},
            ],
            [
                {"stdin": "1 0\n5\n", "expected_stdout": "5"},
                {"stdin": "3 3\n1 2 3\n", "expected_stdout": "1 2 3"},
                {"stdin": "5 1\n9 8 7 6 5\n", "expected_stdout": "5 9 8 7 6"},
            ],
            starter="n, k = map(int, input().split())\narr = list(map(int, input().split()))\n# print rotated array\n",
            marks=20,
            time_seconds=900,
        ),
        _coding(
            (
                "Min Stack Operations Simulation\n"
                "Process operations on a stack that also supports getMin in O(1).\n"
                "Operations: PUSH x | POP | TOP | MIN\n\n"
                "Input:\n"
                "  Line 1: Q\n"
                "  Next Q lines: operations (stack never invalid)\n"
                "Output: for each TOP/MIN, print the value on its own line\n\n"
                "Example 1:\nInput:\n7\nPUSH 3\nPUSH 1\nMIN\nPUSH 2\nTOP\nPOP\nMIN\nOutput:\n1\n2\n1\n\n"
                "Example 2:\nInput:\n4\nPUSH 5\nTOP\nMIN\nPOP\nOutput:\n5\n5"
            ),
            [
                {
                    "stdin": "7\nPUSH 3\nPUSH 1\nMIN\nPUSH 2\nTOP\nPOP\nMIN\n",
                    "expected_stdout": "1\n2\n1",
                },
                {
                    "stdin": "4\nPUSH 5\nTOP\nMIN\nPOP\n",
                    "expected_stdout": "5\n5",
                },
            ],
            [
                {
                    "stdin": "6\nPUSH 2\nPUSH 2\nMIN\nPOP\nMIN\nTOP\n",
                    "expected_stdout": "2\n2\n2",
                },
                {
                    "stdin": "5\nPUSH -1\nPUSH 0\nMIN\nTOP\nPOP\n",
                    "expected_stdout": "-1\n0",
                },
            ],
            starter="q = int(input())\n# process ops; print TOP/MIN results\n",
            marks=30,
        ),
    ]

    pick_subj = _unique_bank_picker(subjective_bank)
    pick_mcq = _unique_bank_picker(mcq_bank)
    pick_msq = _unique_bank_picker(msq_bank)
    pick_num = _unique_bank_picker(numerical_bank)
    pick_code = _unique_bank_picker(coding_bank)

    out: list[dict] = []
    default_time = default_time_seconds()
    for qtype in type_plan:
        if qtype == "mcq":
            base = pick_mcq()
            out.append({**base, "type": "mcq", "time_seconds": default_time, "marks": 10})
        elif qtype == "msq":
            base = pick_msq()
            out.append({**base, "type": "msq", "time_seconds": default_time, "marks": 10})
        elif qtype == "numerical":
            base = pick_num()
            out.append({**base, "type": "numerical", "time_seconds": default_time, "marks": 10})
        elif qtype == "coding":
            base = pick_code()
            out.append({**base, "type": "coding"})
        else:
            out.append(
                {
                    "text": pick_subj(),
                    "type": "subjective",
                    "time_seconds": default_time,
                    "marks": 10,
                }
            )
    return out


def _question_fingerprint(item: dict | str) -> str:
    text = question_text(item).lower()
    text = re.sub(r"\s+", " ", text).strip()
    # Ignore example blocks when comparing — same problem with different examples still dups.
    text = re.split(r"\bexample\s*1\b", text, maxsplit=1)[0].strip()
    return text[:180]


def _dedupe_questions(questions: list[dict]) -> list[dict]:
    """Keep first occurrence of each unique question within an assessment."""
    seen: set[str] = set()
    out: list[dict] = []
    for item in questions:
        key = _question_fingerprint(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _coerce_raw_question(item: object, fallback_type: str) -> dict | None:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return {
            "text": text,
            "type": "subjective" if fallback_type == "subjective" else fallback_type,
            "time_seconds": default_time_seconds(),
            "marks": 10,
        }
    if not isinstance(item, dict):
        return None
    text = question_text(item)
    if not text:
        return None
    qtype = str(item.get("type") or fallback_type or "subjective").strip().lower()
    if qtype not in QUESTION_TYPES:
        qtype = "subjective"
    payload: dict = {
        "text": text,
        "type": qtype,
        "time_seconds": item.get("time_seconds") or default_time_seconds(),
        "marks": item.get("marks") or 10,
    }
    if qtype in ("mcq", "msq"):
        options = item.get("options") or []
        if isinstance(options, list):
            payload["options"] = [str(o).strip() for o in options if str(o).strip()]
        indices = item.get("correct_indices")
        if indices is None and item.get("correct_index") is not None:
            indices = [item.get("correct_index")]
        if isinstance(indices, list):
            payload["correct_indices"] = indices
        elif isinstance(indices, (int, float)):
            payload["correct_indices"] = [int(indices)]
    if qtype == "numerical":
        payload["correct_answer"] = str(item.get("correct_answer") or "").strip()
        payload["tolerance"] = item.get("tolerance", 0)
    if qtype == "coding":
        langs = item.get("languages") or ["python"]
        if isinstance(langs, str):
            langs = [langs]
        payload["languages"] = [str(x).strip().lower() for x in langs if str(x).strip()]
        starter = item.get("starter_code") or {}
        if isinstance(starter, dict):
            payload["starter_code"] = {str(k): str(v) for k, v in starter.items()}
        elif isinstance(starter, str) and starter.strip():
            payload["starter_code"] = {"python": starter}
        payload["public_tests"] = item.get("public_tests") or []
        payload["hidden_tests"] = item.get("hidden_tests") or []
        payload["time_limit_ms"] = item.get("time_limit_ms") or 2000
        payload["memory_limit_mb"] = item.get("memory_limit_mb") or 128
        if item.get("time_seconds"):
            payload["time_seconds"] = item.get("time_seconds")
        else:
            payload["time_seconds"] = max(default_time_seconds(), 600)
        if item.get("marks"):
            payload["marks"] = item.get("marks")
        else:
            payload["marks"] = 20
    return payload


def _questions_from_payload(payload: object, type_plan: list[str]) -> list[dict]:
    items: list = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        raw = payload.get("questions", payload.get("items", []))
        if isinstance(raw, list):
            items = raw

    out: list[dict] = []
    for i, item in enumerate(items):
        fallback = type_plan[i] if i < len(type_plan) else "subjective"
        coerced = _coerce_raw_question(item, fallback)
        if coerced:
            out.append(coerced)
    return out


def _parse_questions_from_llm_text(
    content: str,
    question_count: int,
    jd_text: str,
    difficulty: str,
    question_types: list[str] | None = None,
) -> list[dict]:
    text = _strip_markdown_code_block(content)
    type_plan = _distribute_types(question_count, question_types or ["subjective"])
    cleaned: list[dict] = []

    try:
        payload = json.loads(text)
        cleaned = _questions_from_payload(payload, type_plan)
    except json.JSONDecodeError:
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = text.find(opener), text.rfind(closer) + 1
            if start >= 0 and end > start:
                try:
                    payload = json.loads(text[start:end])
                    cleaned = _questions_from_payload(payload, type_plan)
                    if cleaned:
                        break
                except json.JSONDecodeError:
                    continue

    validated: list[dict] = []
    for item in cleaned:
        try:
            q = AssessmentQuestion.model_validate(normalize_question(item))
            validated.append(q.model_dump(exclude_none=True))
        except Exception:
            # Downgrade invalid objective items to subjective text-only
            text_only = question_text(item)
            if text_only:
                validated.append(
                    {
                        "text": text_only,
                        "type": "subjective",
                        "time_seconds": default_time_seconds(),
                        "marks": 10,
                    }
                )

    validated = _dedupe_questions(validated)
    if len(validated) < question_count:
        seen = {_question_fingerprint(q) for q in validated}
        fallback = _fallback_question_dicts(
            jd_text, question_count * 2, difficulty, question_types
        )
        for item in fallback:
            if len(validated) >= question_count:
                break
            key = _question_fingerprint(item)
            if key in seen:
                continue
            seen.add(key)
            validated.append(item)

    return _dedupe_questions(validated)[:question_count]


def _mark_origin(item: dict, origin: str) -> dict:
    out = dict(item)
    out["origin"] = origin
    if origin == "ai":
        out.pop("bank_id", None)
    return out


def _compose_from_question_bank(
    jd_text: str,
    question_count: int,
    difficulty: str,
    question_types: list[str] | None,
    recruiter_id: int | None,
) -> list[dict]:
    from app.services.question_bank_service import (
        extract_skill_tags,
        retrieve_bank_questions,
    )

    types = question_types or ["subjective"]
    type_plan = _distribute_types(question_count, types)
    skills = extract_skill_tags(jd_text)
    needed_types = list(dict.fromkeys(type_plan))
    pools = retrieve_bank_questions(
        question_types=needed_types,
        difficulty=difficulty,
        skill_tags=skills,
        limit_per_type=max(question_count, 8),
        recruiter_id=recruiter_id,
    )
    cursors: dict[str, int] = {t: 0 for t in needed_types}
    chosen: list[dict] = []
    seen: set[str] = set()

    for qtype in type_plan:
        pool = pools.get(qtype) or []
        idx = cursors.get(qtype, 0)
        picked = None
        while idx < len(pool):
            candidate = pool[idx]
            idx += 1
            key = _question_fingerprint(candidate)
            if not key or key in seen:
                continue
            picked = candidate
            seen.add(key)
            break
        cursors[qtype] = idx
        if picked is not None:
            chosen.append(_mark_origin(picked, "library"))

    return chosen


def _llm_fill_gaps(
    jd_text: str,
    gap_count: int,
    difficulty: str,
    gap_types: list[str],
    examples: list[dict],
) -> list[dict]:
    if gap_count <= 0:
        return []
    type_counts: dict[str, int] = {}
    for t in gap_types:
        type_counts[t] = type_counts.get(t, 0) + 1
    mix_desc = ", ".join(f"{count} {name}" for name, count in type_counts.items())
    example_blob = json.dumps(examples[:4], ensure_ascii=True)[:3500]

    system_prompt = (
        "You are a senior technical interviewer creating assessment questions. "
        "Generate clear, NON-REPETITIVE questions based ONLY on the job description. "
        "Use the style of the provided library examples but create NEW distinct questions. "
        "Support types: subjective, mcq, msq, numerical, coding. "
        "For coding include Example 1/Example 2 I/O, public_tests and hidden_tests. "
        'Return ONLY valid JSON {"questions": [...]}.'
    )
    user_prompt = (
        f"Difficulty level: {difficulty}\n"
        f"Number of NEW questions: {gap_count}\n"
        f"Requested mix: {mix_desc}\n"
        f"Preferred type order: {gap_types}\n\n"
        f"Library style examples (do not copy):\n{example_blob}\n\n"
        f"Job Description:\n{jd_text.strip()}\n"
    )
    try:
        response = groq_chat_completion(
            model=settings.GROQ_MODEL,
            temperature=0.7,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ""
    except AIException:
        # Bank-first path: fall back so recruiters still get a draft.
        return [
            _mark_origin(q, "ai")
            for q in _fallback_question_dicts(
                jd_text, gap_count, difficulty, list(dict.fromkeys(gap_types))
            )[:gap_count]
        ]

    if not content.strip():
        return [
            _mark_origin(q, "ai")
            for q in _fallback_question_dicts(
                jd_text, gap_count, difficulty, list(dict.fromkeys(gap_types))
            )[:gap_count]
        ]

    parsed = _parse_questions_from_llm_text(
        content, gap_count, jd_text, difficulty, list(dict.fromkeys(gap_types)) or None
    )
    if not parsed:
        return [
            _mark_origin(q, "ai")
            for q in _fallback_question_dicts(
                jd_text, gap_count, difficulty, list(dict.fromkeys(gap_types))
            )[:gap_count]
        ]
    return [_mark_origin(q, "ai") for q in parsed]


def generate_questions_from_jd(
    jd_text: str,
    question_count: int,
    difficulty: str,
    question_types: list[str] | None = None,
    *,
    use_question_bank: bool = True,
    recruiter_id: int | None = None,
) -> list[dict]:
    """Generate interview questions from a job description (library-first by default)."""
    types = question_types or ["subjective"]
    type_plan = _distribute_types(question_count, types)

    composed: list[dict] = []
    if use_question_bank:
        composed = _compose_from_question_bank(
            jd_text, question_count, difficulty, question_types, recruiter_id
        )

    if len(composed) >= question_count:
        return _dedupe_questions(composed)[:question_count]

    remaining_types = type_plan[len(composed) :]
    gap = question_count - len(composed)
    llm_extra = _llm_fill_gaps(
        jd_text,
        gap,
        difficulty,
        remaining_types,
        examples=composed[:6],
    )
    seen = {_question_fingerprint(q) for q in composed}
    for item in llm_extra:
        key = _question_fingerprint(item)
        if not key or key in seen:
            continue
        seen.add(key)
        composed.append(item)
        if len(composed) >= question_count:
            break

    if len(composed) < question_count:
        fallback = _fallback_question_dicts(
            jd_text, question_count * 2, difficulty, question_types
        )
        for item in fallback:
            key = _question_fingerprint(item)
            if not key or key in seen:
                continue
            seen.add(key)
            composed.append(_mark_origin(item, "ai"))
            if len(composed) >= question_count:
                break

    return _dedupe_questions(composed)[:question_count]


def generate_questions_from_jd_ai_only(
    jd_text: str,
    question_count: int,
    difficulty: str,
    question_types: list[str] | None = None,
) -> list[dict]:
    """Legacy Groq-first generation path (AI-only mode)."""
    types = question_types or ["subjective"]
    type_plan = _distribute_types(question_count, types)
    type_counts: dict[str, int] = {}
    for t in type_plan:
        type_counts[t] = type_counts.get(t, 0) + 1
    mix_desc = ", ".join(f"{count} {name}" for name, count in type_counts.items())

    system_prompt = (
        "You are a senior technical interviewer creating assessment questions. "
        "Generate clear, NON-REPETITIVE questions based ONLY on the job description. "
        "Do not assume any candidate resume. "
        "Prefer harder, modern interview questions when difficulty is Medium/Hard or count is high. "
        "Avoid near-duplicate prompts — each question must test a distinct skill or concept. "
        "Support types: subjective (open-ended), mcq (one correct), "
        "msq (multi-select), numerical (exact/tolerance answer), "
        "coding (stdin/stdout programming problem). "
        "For mcq/msq provide 4 plausible options and correct_indices. "
        "For numerical provide correct_answer and optional tolerance. "
        "For coding: create REAL interview-style DSA problems (HackerRank/LeetCode Medium+), "
        "NOT trivial sum/reverse/hello-world tasks. Prefer hash maps, stacks, heaps, two pointers, "
        "sliding window, prefix sums, intervals, binary search, or greedy. "
        "Each coding question text MUST include clear Input/Output format, constraints, and "
        "exactly two worked examples. "
        "languages subset of [c, cpp, python, java, javascript] (omit perl), "
        "minimal starter_code stubs (do NOT give the full solution), "
        "public_tests and hidden_tests as [{stdin, expected_stdout}], "
        "time_seconds 900-1500, marks 20-30, time_limit_ms around 5000. "
        "Do not include numbering prefixes in question text."
    )
    user_prompt = (
        f"Difficulty level: {difficulty}\n"
        f"Number of questions: {question_count}\n"
        f"Requested mix: {mix_desc}\n"
        f"Preferred type order (one per question): {type_plan}\n\n"
        f"Job Description:\n{jd_text.strip()}\n\n"
        "Return ONLY valid JSON with a questions array."
    )

    try:
        response = groq_chat_completion(
            model=settings.GROQ_MODEL,
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

    if not content.strip():
        raise AIException("Generation failed. Please try again.")

    parsed = _parse_questions_from_llm_text(
        content, question_count, jd_text, difficulty, question_types
    )
    if not parsed:
        raise AIException("Generation failed. Please try again.")
    return [_mark_origin(q, "ai") for q in parsed]


def _to_assessment_questions(raw: list) -> list[AssessmentQuestion]:
    questions: list[AssessmentQuestion] = []
    for item in normalize_questions(raw):
        try:
            questions.append(AssessmentQuestion.model_validate(item))
        except Exception:
            questions.append(
                AssessmentQuestion(
                    text=item["text"],
                    type="subjective",
                    time_seconds=int(item.get("time_seconds") or default_time_seconds()),
                    marks=float(item.get("marks") or 10),
                    origin=item.get("origin"),
                    bank_id=item.get("bank_id"),
                )
            )
    return questions


def _questions_payload(questions: list[AssessmentQuestion]) -> list[dict]:
    return [q.model_dump(exclude_none=True) for q in questions]


def _summary_from_invite(invite: InterviewInvite, now: datetime) -> AssessmentSummary:
    jd_lines = invite.jd_text.strip().splitlines()
    role_preview = (jd_lines[0][:80] if jd_lines else "Assessment").strip()
    questions = normalize_questions(list(invite.questions_json or []))
    expiry = _as_aware_utc(invite.expiry_at)
    created = _as_aware_utc(invite.created_at)
    return AssessmentSummary(
        token=invite.token,
        invite_link=f"/interview/invite/{invite.token}",
        role_preview=role_preview,
        difficulty=invite.difficulty,
        question_count=len(questions),
        expiry_at=expiry,
        used_count=invite.used_count,
        max_uses=invite.max_uses,
        created_at=created,
        is_expired=expiry <= now,
        duration_minutes=getattr(invite, "duration_minutes", None),
    )


class AssessmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def generate_questions_preview(
        data: GenerateQuestionsRequest,
        recruiter_id: int | None = None,
    ) -> GenerateQuestionsResponse:
        if data.use_question_bank:
            raw = generate_questions_from_jd(
                data.jd_text,
                data.question_count,
                data.difficulty,
                data.question_types,
                use_question_bank=True,
                recruiter_id=recruiter_id,
            )
        else:
            raw = generate_questions_from_jd_ai_only(
                data.jd_text,
                data.question_count,
                data.difficulty,
                data.question_types,
            )
        questions = _to_assessment_questions(raw)
        return GenerateQuestionsResponse(questions=questions, jd_text=data.jd_text)

    async def create_assessment(
        self,
        recruiter_id: int,
        data: CreateAssessmentRequest,
    ) -> CreateAssessmentResponse:
        if data.questions:
            questions = data.questions
        else:
            raw = generate_questions_from_jd(
                data.jd_text,
                data.question_count,
                data.difficulty,
                data.question_types,
                use_question_bank=True,
                recruiter_id=recruiter_id,
            )
            questions = _to_assessment_questions(raw)

        token = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expiry_at = now + timedelta(hours=data.expiry_hours)

        invite = InterviewInvite(
            token=token,
            recruiter_id=recruiter_id,
            jd_text=data.jd_text,
            questions_json=_questions_payload(questions),
            difficulty=data.difficulty,
            expiry_at=expiry_at,
            max_uses=data.max_uses,
            used_count=0,
            created_at=now,
            duration_minutes=data.duration_minutes,
        )
        self.db.add(invite)
        await self.db.commit()

        bank_ids = [int(q.bank_id) for q in questions if q.bank_id]
        if bank_ids:
            from app.services.question_bank_service import record_question_bank_usage

            record_question_bank_usage(
                recruiter_id=recruiter_id,
                invite_token=token,
                bank_ids=bank_ids,
            )

        from app.services.invite_funnel import record_invite_funnel_event

        record_invite_funnel_event(
            invite_token=token,
            event_type="created",
            metadata={"difficulty": data.difficulty, "question_count": len(questions)},
        )

        invite_link = f"/interview/invite/{token}"
        return CreateAssessmentResponse(
            token=token,
            invite_link=invite_link,
            questions_preview=questions,
        )


    async def list_assessments(self, recruiter_id: int) -> list[AssessmentSummary]:
        result = await self.db.execute(
            select(InterviewInvite)
            .where(
                InterviewInvite.recruiter_id == recruiter_id,
                InterviewInvite.deleted_at.is_(None),
            )
            .order_by(InterviewInvite.created_at.desc())
        )
        now = datetime.now(timezone.utc)
        return [_summary_from_invite(row, now) for row in result.scalars().all()]

    async def delete_assessment(self, recruiter_id: int, token: str) -> None:
        """Soft-delete an assessment owned by the recruiter.

        Soft-delete avoids FK failures from invite_funnel_events /
        candidate_verifications / identity_verification_attempts, and keeps the
        invite row so recruiter session ownership (via invite_token) still works.
        """
        result = await self.db.execute(
            select(InterviewInvite).where(InterviewInvite.token == token)
        )
        invite = result.scalar_one_or_none()
        if invite is None or invite.recruiter_id != recruiter_id:
            raise NotFoundException("Assessment not found")
        if invite.deleted_at is not None:
            raise NotFoundException("Assessment not found")
        invite.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def update_assessment(
        self,
        recruiter_id: int,
        token: str,
        data: UpdateAssessmentRequest,
    ) -> AssessmentSummary:
        result = await self.db.execute(
            select(InterviewInvite).where(InterviewInvite.token == token)
        )
        invite = result.scalar_one_or_none()
        if (
            invite is None
            or invite.recruiter_id != recruiter_id
            or invite.deleted_at is not None
        ):
            raise NotFoundException("Assessment not found")
        if data.expiry_hours is not None:
            invite.expiry_at = datetime.now(timezone.utc) + timedelta(
                hours=data.expiry_hours
            )
        await self.db.commit()
        await self.db.refresh(invite)
        now = datetime.now(timezone.utc)
        return _summary_from_invite(invite, now)

    async def send_assessment_invites(
        self,
        recruiter_id: int,
        token: str,
        data: SendAssessmentInvitesRequest,
    ) -> SendAssessmentInvitesResponse:
        result = await self.db.execute(
            select(InterviewInvite).where(InterviewInvite.token == token)
        )
        invite = result.scalar_one_or_none()
        if (
            invite is None
            or invite.recruiter_id != recruiter_id
            or invite.deleted_at is not None
        ):
            raise NotFoundException("Assessment not found")
        now = datetime.now(timezone.utc)
        summary = _summary_from_invite(invite, now)
        if summary.is_expired:
            raise ConflictException("This assessment invite has expired.")

        invite_path = summary.invite_link
        invite_url = f"{settings.effective_frontend_url}{invite_path}"
        failed: list[str] = []
        sent = 0
        for email in data.emails:
            ok = send_assessment_invite_email(
                email,
                invite_url=invite_url,
                role_preview=summary.role_preview,
                recruiter_note=data.message,
            )
            if ok:
                sent += 1
            else:
                failed.append(email)
        return SendAssessmentInvitesResponse(
            sent=sent,
            failed=failed,
            invite_link=invite_path,
            delivery_note=smtp_delivery_hint(any_failed=bool(failed)),
        )
