#!/usr/bin/env python3
"""Generate app/data/question_bank_seed.json with curated industry-style items."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "data" / "question_bank_seed.json"
import sys

sys.path.insert(0, str(ROOT))


def _slug(title: str, idx: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or "item"
    digest = hashlib.sha1(f"{idx}:{title}".encode()).hexdigest()[:8]
    return f"seed-{base}-{digest}"


def coding(
    title: str,
    body: str,
    public: list,
    hidden: list,
    tags: list[str],
    difficulty: str,
    starter: str | None = None,
    marks: int = 25,
    time_seconds: int = 1200,
) -> dict:
    text = body.strip() + "\n"
    return {
        "type": "coding",
        "difficulty": difficulty,
        "title": title,
        "prompt_text": text,
        "skill_tags": tags,
        "role_tags": ["sde"],
        "payload": {
            "text": text,
            "type": "coding",
            "languages": ["python", "javascript", "java", "cpp", "c"],
            "starter_code": {
                "python": starter or "# Read from stdin, write to stdout\n"
            },
            "public_tests": public,
            "hidden_tests": hidden,
            "time_seconds": time_seconds,
            "marks": marks,
            "time_limit_ms": 5000,
            "memory_limit_mb": 128,
        },
        "source": "seed",
        "quality_score": 1.0,
    }


def mcq(title, text, options, correct, tags, difficulty="Medium"):
    return {
        "type": "mcq",
        "difficulty": difficulty,
        "title": title,
        "prompt_text": text,
        "skill_tags": tags,
        "role_tags": ["sde"],
        "payload": {
            "text": text,
            "type": "mcq",
            "options": options,
            "correct_indices": correct,
            "time_seconds": 120,
            "marks": 10,
        },
        "source": "seed",
        "quality_score": 1.0,
    }


def msq(title, text, options, correct, tags, difficulty="Medium"):
    return {
        "type": "msq",
        "difficulty": difficulty,
        "title": title,
        "prompt_text": text,
        "skill_tags": tags,
        "role_tags": ["sde"],
        "payload": {
            "text": text,
            "type": "msq",
            "options": options,
            "correct_indices": correct,
            "time_seconds": 120,
            "marks": 10,
        },
        "source": "seed",
        "quality_score": 1.0,
    }


def numerical(title, text, answer, tags, difficulty="Easy", tol=0):
    return {
        "type": "numerical",
        "difficulty": difficulty,
        "title": title,
        "prompt_text": text,
        "skill_tags": tags,
        "role_tags": ["sde"],
        "payload": {
            "text": text,
            "type": "numerical",
            "correct_answer": str(answer),
            "tolerance": tol,
            "time_seconds": 90,
            "marks": 10,
        },
        "source": "seed",
        "quality_score": 1.0,
    }


def subjective(title, text, tags, difficulty="Medium"):
    return {
        "type": "subjective",
        "difficulty": difficulty,
        "title": title,
        "prompt_text": text,
        "skill_tags": tags,
        "role_tags": ["sde"],
        "payload": {
            "text": text,
            "type": "subjective",
            "time_seconds": 180,
            "marks": 10,
        },
        "source": "seed",
        "quality_score": 1.0,
    }


def build_items() -> list[dict]:
    items: list[dict] = []

    # Import compact coding specs from companion module to keep this file maintainable.
    from app.data.question_bank_coding_specs import CODING_SPECS  # type: ignore

    for spec in CODING_SPECS:
        items.append(coding(*spec))

    mcqs = [
        ("Maintainability", "Which practice best improves long-term code maintainability?", ["Clear naming and small focused functions", "Copy-pasting proven snippets everywhere", "Avoiding code reviews to move faster", "Keeping all logic in one module"], [0], ["testing", "backend"]),
        ("Automated Tests Goal", "What is the primary goal of writing automated tests?", ["Increase deploy confidence and catch regressions early", "Replace all manual QA forever", "Make the codebase larger on purpose", "Slow down every feature release"], [0], ["testing"]),
        ("Incident First Step", "In a production incident, what should you do first?", ["Stabilize impact and communicate status", "Rewrite the system from scratch", "Ignore metrics and wait", "Delete logs to reduce noise"], [0], ["devops", "backend"]),
        ("HTTP Created", "Which HTTP status best indicates a successful resource creation?", ["201 Created", "204 No Content", "301 Moved Permanently", "409 Conflict"], [0], ["backend"]),
        ("CAP Theorem", "What does CAP theorem say a distributed system cannot guarantee simultaneously?", ["Consistency, Availability, and Partition tolerance", "Caching, Auth, and Pagination", "CPU, Memory, and Disk", "Latency, Throughput, and Cost"], [0], ["system-design"]),
        ("Index Equality", "Which index type is typically best for equality lookups on a high-cardinality column?", ["B-tree / hash index", "Full table scan only", "Bitmap on unique UUID", "No index needed"], [0], ["databases"]),
        ("Idempotent APIs", "What is the main benefit of idempotent API design?", ["Safe retries without unintended duplicate side effects", "Faster JSON parsing", "Smaller Docker images", "Automatic schema migrations"], [0], ["backend"]),
        ("Secrets CI", "Which approach best prevents secret leakage in CI/CD?", ["Store secrets in a vault / secret manager, inject at runtime", "Commit .env files for convenience", "Put secrets in public README examples", "Hard-code keys in frontend bundles"], [0], ["security", "devops"]),
        ("REST Safe Method", "Which HTTP method is considered safe and idempotent?", ["GET", "POST", "PATCH", "CONNECT"], [0], ["backend"]),
        ("ACID Atomicity", "In ACID, atomicity means:", ["All operations in a transaction succeed or none do", "Data is never encrypted", "Indexes are always used", "Replicas are eventually consistent"], [0], ["databases"]),
        ("N Plus One", "What is the N+1 query problem?", ["Fetching related rows with one query per parent after the initial query", "Using too many CPU cores", "Having N+1 microservices", "A CSS layout bug"], [0], ["databases", "backend"]),
        ("JWT Purpose", "What is a common purpose of JWT in APIs?", ["Stateless authentication / authorization claims", "Compressing images", "Scheduling cron jobs", "Replacing TLS"], [0], ["security", "backend"]),
        ("Horizontal Scale", "Horizontal scaling primarily means:", ["Adding more machines/instances", "Increasing CPU on one machine", "Deleting caches", "Rewriting in assembly"], [0], ["system-design"]),
        ("CDN Benefit", "A CDN primarily helps by:", ["Caching static assets closer to users", "Replacing databases", "Encrypting SQL queries", "Running unit tests"], [0], ["system-design", "cloud"]),
        ("Blue Green", "Blue/green deployment reduces risk by:", ["Switching traffic between two complete environments", "Editing production code live", "Skipping staging", "Disabling monitoring"], [0], ["devops"]),
        ("Optimistic Lock", "Optimistic locking typically uses:", ["Version numbers / ETags to detect concurrent writes", "Only table locks forever", "Deleting the row on read", "Disabling transactions"], [0], ["databases", "backend"]),
        ("Rate Limiting", "Rate limiting protects services by:", ["Restricting request volume per client/key", "Increasing payload size", "Removing authentication", "Disabling retries"], [0], ["backend", "security"]),
        ("Eventual Consistency", "Eventual consistency means:", ["Replicas converge to the same state given enough time without updates", "All reads are always linearizable", "Writes never succeed", "Caches are never used"], [0], ["system-design"]),
        ("OAuth Role", "OAuth 2.0 is primarily designed for:", ["Delegated authorization", "Compressing JSON", "Schema migration", "Packet routing"], [0], ["security"]),
        ("SQL Injection Defense", "Best defense against SQL injection:", ["Parameterized queries / prepared statements", "String concatenation of user input", "Disabling HTTPS", "Using GET for all writes"], [0], ["security", "databases"]),
        ("Load Balancer L7", "Layer-7 load balancers can route based on:", ["HTTP path/host/headers", "Only MAC addresses", "Only disk RPM", "CSS selectors"], [0], ["system-design"]),
        ("Cache Stampede", "A cache stampede happens when:", ["Many clients miss simultaneously and overload the origin", "TTL is infinite", "Only one key exists", "DNS is perfect"], [0], ["system-design"]),
        ("Circuit Breaker", "Circuit breakers help by:", ["Failing fast when a dependency is unhealthy", "Deleting all logs", "Increasing timeouts forever", "Disabling alerts"], [0], ["backend", "system-design"]),
        ("Twelve Factor Config", "Twelve-Factor apps store config in:", ["Environment variables", "Hard-coded constants only", "Binary blobs in git", "Client localStorage"], [0], ["devops", "backend"]),
        ("Postgres Vacuum", "VACUUM in PostgreSQL primarily:", ["Reclaims storage and maintains visibility map health", "Creates users", "Shuts down replicas", "Encrypts disks"], [0], ["databases"]),
        ("React Key Prop", "React list keys should be:", ["Stable unique identifiers among siblings", "Array index always even if reordered", "Random on every render", "Empty strings"], [0], ["frontend"]),
        ("Python GIL", "The CPython GIL primarily limits:", ["CPU-bound multi-threaded parallelism in one process", "Disk encryption", "JSON encoding speed always", "DNS resolution"], [0], ["python"]),
        ("Kafka Consumer Group", "In Kafka, a consumer group:", ["Shares partitions of a topic for parallel consume", "Deletes topics automatically", "Replaces ZooKeeper always", "Encrypts disks"], [0], ["queue", "backend"]),
        ("TLS Purpose", "TLS primarily provides:", ["Encryption and authenticity for data in transit", "Faster SQL joins", "Automatic sharding", "UI theming"], [0], ["security"]),
        ("Observability Pillars", "The three common observability pillars are:", ["Metrics, logs, and traces", "CSS, HTML, and JS", "CPU, GPU, and RAM", "Git, Docker, and npm"], [0], ["devops", "system-design"]),
    ]
    for row in mcqs:
        items.append(mcq(*row))

    msqs = [
        ("API Reliability", "Which of the following improve API reliability? Select all that apply.", ["Timeouts and retries with backoff", "Input validation", "Hard-coding secrets in source", "Health checks and monitoring"], [0, 1, 3], ["backend"]),
        ("Secure Delivery", "Which practices support secure software delivery? Select all that apply.", ["Least-privilege access", "Dependency vulnerability scanning", "Sharing production credentials in chat", "Encrypted secrets storage"], [0, 1, 3], ["security", "devops"]),
        ("Perf Diagnosis", "Which techniques help diagnose production performance issues? Select all that apply.", ["Profiling hot paths", "Checking slow-query logs", "Ignoring p99 latency", "Load testing representative traffic"], [0, 1, 3], ["devops", "databases"]),
        ("Message Queue Reasons", "Which are valid reasons to choose a message queue? Select all that apply.", ["Decouple producers and consumers", "Absorb traffic spikes", "Guarantee UI pixel-perfect rendering", "Enable asynchronous processing"], [0, 1, 3], ["queue", "system-design"]),
        ("Good Indexes", "Which statements about database indexes are true? Select all that apply.", ["They can speed up reads", "They can slow down writes", "They always remove the need for EXPLAIN", "Composite indexes can support multi-column filters"], [0, 1, 3], ["databases"]),
        ("Cloud Cost Control", "Which help control cloud costs? Select all that apply.", ["Right-sizing instances", "Turning off unused environments", "Always using the largest GPU", "Budgets and anomaly alerts"], [0, 1, 3], ["cloud", "devops"]),
        ("REST Design", "Which are REST best practices? Select all that apply.", ["Use nouns for resources", "Use proper HTTP verbs/status codes", "Put secrets in query strings", "Version APIs thoughtfully"], [0, 1, 3], ["backend"]),
        ("CI Pipeline", "Which belong in a solid CI pipeline? Select all that apply.", ["Automated tests", "Lint/static analysis", "Manual production password paste in logs", "Artifact build"], [0, 1, 3], ["devops", "testing"]),
        ("Data Privacy", "Which protect user data privacy? Select all that apply.", ["Encryption at rest", "Access audits", "Publishing PII in analytics dashboards publicly", "Data retention limits"], [0, 1, 3], ["security"]),
        ("Frontend Perf", "Which improve web frontend performance? Select all that apply.", ["Code splitting", "Image optimization", "Blocking the main thread with huge sync work", "Caching static assets"], [0, 1, 3], ["frontend"]),
        ("SRE Practices", "Which are common SRE practices? Select all that apply.", ["SLIs/SLOs", "Error budgets", "Ignoring on-call handoffs", "Blameless postmortems"], [0, 1, 3], ["devops", "system-design"]),
        ("Python Packaging", "Which are true about Python dependency management? Select all that apply.", ["Pin versions for reproducible builds", "Use virtual environments", "Commit secrets inside wheels", "Prefer audited package sources"], [0, 1, 3], ["python", "devops"]),
        ("Graph Algorithms", "Which algorithms commonly traverse graphs? Select all that apply.", ["BFS", "DFS", "Quicksort on edges only always", "Dijkstra for weighted shortest paths"], [0, 1, 3], ["graphs"]),
        ("Cache Strategies", "Which are valid caching strategies? Select all that apply.", ["Cache-aside", "Write-through", "Store plaintext passwords only in cache", "TTL expiration"], [0, 1, 3], ["system-design"]),
        ("AuthN AuthZ", "Which statements are correct? Select all that apply.", ["Authentication verifies identity", "Authorization checks permissions", "TLS replaces authorization completely", "MFA strengthens authentication"], [0, 1, 3], ["security"]),
    ]
    for row in msqs:
        items.append(msq(*row))

    nums = [
        ("RPS to Hour", "A service handles 120 requests/minute. How many requests is that per hour?", 7200, ["backend"]),
        ("Latency Ms", "An API has p95 latency of 0.25 seconds. What is that latency in milliseconds?", 250, ["backend"]),
        ("Points Per Week", "A team completes 8 story points in a 2-week sprint. What is average points per week?", 4, ["testing"]),
        ("Cache Hits", "A cache hit rate is 80% of 5000 lookups. How many hits is that?", 4000, ["system-design"]),
        ("Log2 Comparisons", "A binary search on a sorted array of 1,048,576 elements takes at most how many comparisons (log2 N)?", 20, ["binary-search"]),
        ("Cron Runs", "If a job runs every 15 minutes, how many runs occur in 24 hours?", 96, ["devops"]),
        ("Percent Failures", "Out of 2000 requests, 50 failed. What is the failure rate in percent?", 2.5, ["backend"], "Easy", 0.01),
        ("Shard Size", "1,000,000 rows across 8 equal shards. Rows per shard?", 125000, ["databases"]),
        ("Bandwidth", "Transfer 500 MB at 100 MB/s. Seconds needed?", 5, ["system-design"]),
        ("Replication Lag", "Primary write at t=0, replica lags 3s. Earliest safe read-your-write wait seconds?", 3, ["databases", "system-design"]),
        ("Thread Pool", "Pool size 20, each task 200ms CPU. Approx max tasks/sec if fully utilized?", 100, ["backend"]),
        ("SLA Monthly", "99.9% monthly uptime allows how many downtime minutes in a 30-day month? (approx floor)", 43, ["devops"], "Medium", 1),
    ]
    for row in nums:
        if len(row) == 4:
            items.append(numerical(*row))
        else:
            items.append(numerical(row[0], row[1], row[2], row[3], row[4], row[5]))

    subs = [
        ("Relevant Experience", "Describe the most relevant project experience you bring for this role and why it maps to the job description.", ["backend", "system-design"]),
        ("Production Debug", "Walk through how you would debug and resolve a production incident under time pressure.", ["devops", "backend"]),
        ("Tradeoff Decision", "Describe a technical decision you made, the tradeoffs you considered, and the outcome.", ["system-design"]),
        ("Learning Approach", "How do you approach learning a new framework required for a role like this?", ["backend"]),
        ("Nontechnical Explain", "Explain a complex concept from this job description as you would to a non-technical stakeholder.", ["system-design"]),
        ("Legacy Onboarding", "Describe your approach to onboarding onto an unfamiliar legacy codebase.", ["backend"]),
        ("Tech Debt", "How do you balance technical debt reduction with feature delivery?", ["backend", "testing"]),
        ("Perf Optimization", "Explain a performance optimization you made and how you measured impact.", ["backend", "databases"]),
        ("Stakeholder Conflict", "Tell me about a time you disagreed with a technical approach. How did you resolve it?", ["backend"]),
        ("Scalable Design", "How would you design a scalable component related to this role? What bottlenecks would you watch?", ["system-design"]),
        ("Code Quality Deadline", "How do you ensure code quality when shipping under a tight deadline?", ["testing", "backend"]),
        ("Distributed Failures", "Walk through investigating intermittent failures in a distributed system.", ["system-design", "devops"]),
        ("Collaboration", "Tell me about collaborating across teams to deliver a feature end to end.", ["backend"]),
        ("Prioritization", "How do you prioritize when multiple stakeholders have competing deadlines?", ["backend"]),
        ("Security Mindset", "How do you incorporate security into day-to-day development?", ["security"]),
        ("Data Modeling", "Describe how you would model data for a high-read feature in this domain.", ["databases"]),
        ("API Design Story", "Describe an API you designed and how you evolved it without breaking clients.", ["backend"]),
        ("Observability Habit", "How do you use metrics/logs/traces in your daily debugging workflow?", ["devops"]),
    ]
    for row in subs:
        items.append(subjective(*row))

    for idx, item in enumerate(items):
        item["slug"] = _slug(item["title"], idx)
    return items


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    items = build_items()
    OUT.write_text(json.dumps(items, indent=2), encoding="utf-8")
    counts: dict[str, int] = {}
    for item in items:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
    print(f"Wrote {len(items)} items -> {OUT}")
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
