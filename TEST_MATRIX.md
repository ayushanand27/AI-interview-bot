# Reliability test matrix — industry-ready on free tier

Correctness + graceful failure only. No new product features.
Baseline pass: post-hardening working tree (auth, ATS, Groq retry, invite, proctor, live WS, dashboard, DSAR, hosting).

Status legend: **PASS** (already OK) · **FIXED** (fixed in this pass) · **LIMIT** (needs paid/infra, out of scope)

---

## 1. Auth flow

| Case | Status | Notes |
|------|--------|-------|
| Invalid email format | PASS / FIXED | Clear validation messages on register/login |
| Wrong password | PASS / FIXED | Distinct wrong-credentials message |
| Expired / invalid verify link | PASS / FIXED | Explicit expired/invalid copy |
| SMTP failure during signup | FIXED | Signup does not look “hung”; delivery note / clear failure |
| Forgot → reset password | PASS / FIXED | Reset errors surfaced in UI |
| Blank page / generic 500 | FIXED | Auth exception paths return user-facing messages |

## 2. Jobs + apply + ATS shortlist

| Case | Status | Notes |
|------|--------|-------|
| Empty resume upload | PASS / FIXED | Client requires file; server rejects empty |
| Scanned / image-only PDF | FIXED | Parse failure → unable-to-parse style score/message, no crash |
| Corrupted / huge file | FIXED | Resume parser + job apply catch oversized/corrupt |
| Non-English resume | PASS | Keyword ATS may score low; does not crash |
| Shortlist scoring edge resume | FIXED | `ats_scoring` / parser hardened against empty text |

## 3. Assessment creation (Groq)

| Case | Status | Notes |
|------|--------|-------|
| Groq timeout | FIXED | Timeout + clear generation failed message |
| Groq rate limit | FIXED | One automatic retry, then clear try-again |
| Malformed LLM JSON | FIXED / PASS | Parse fallback + recruiter error, spinner cleared |
| Stuck spinner | FIXED | Recruiter UI always clears loading on failure |

## 4. Invite flow

| Case | Status | Notes |
|------|--------|-------|
| Camera permission denied | FIXED | Clear `getMediaErrorMessage` on identity + checklist |
| Mic permission denied | FIXED | Same |
| Invite expired | PASS | Clear invalid screen |
| Max-uses exhausted | FIXED | Block resume abuse on single-use; login path for in-progress |
| Network drop mid-interview | FIXED | Fetch failures → retryable network message |
| Browser refresh mid-session | FIXED | sessionStorage restore → checklist; drafts kept; no infinite load |
| Frozen screen | FIXED | Always next step or support-oriented message |

## 5. Proctoring

| Case | Status | Notes |
|------|--------|-------|
| YOLO lag on low CPU | FIXED | 3s detect timeout, non-blocking, skip if busy |
| Detector unavailable | PASS | Fail-soft |
| No face / poor lighting | PASS / FIXED | No session crash; NaN confidence hardened |
| Integrity score edge values | FIXED | NaN/inf rejected; penalty clamp retained |
| Extended no-face | PASS | Accumulates minor/moderate penalties, no hang |

## 6. Anti-cheat

| Case | Status | Notes |
|------|--------|-------|
| Copy/paste block attached (Chrome/Edge) | PASS | Handlers present; intentional paste block |
| Watermark / blur-on-blur | PASS | Active in interview room |
| LLM paste canary | PASS | Canary wrap present |
| False positive blocks submit | PASS | No clear submit-blocking bug found |

## 7. Live collaborative rooms

| Case | Status | Notes |
|------|--------|-------|
| WS drop + recovery | FIXED | Reconnect with backoff |
| Disconnected UI | FIXED | Connecting / reconnecting / disconnected banners |
| Bad JSON message | FIXED | Client + server dict guards |
| Chat/code resync after reconnect | FIXED | hello state + local code push |
| Multi-worker / multi-instance sync | LIMIT | In-memory rooms — needs Redis (out of scope) |
| Process restart mid-room | LIMIT | State lost without Redis |

## 8. Recruiter dashboard / PDF / analytics

| Case | Status | Notes |
|------|--------|-------|
| PDF with missing/partial session | FIXED | Report generator tolerates partial data |
| Analytics zero sessions | FIXED | No NaN / blank crash paths |
| High-session recruiter | PASS / FIXED | Aggregations hardened |
| PDF generation failure UI | FIXED | Clear error to recruiter |

## 9. Retention / DSAR

| Case | Status | Notes |
|------|--------|-------|
| TTL cleanup cron on EC2 | PASS | Crontab present: `0 3 * * *` → `cleanup_retention.py --execute`; log at `logs/retention_cleanup.log` |
| DSAR export end-to-end | FIXED | Privacy API/UI clearer success/error |
| DSAR delete/anonymize | FIXED | Real delete path; errors surfaced (not silent log-only) |

## 10. Hosting reliability

| Case | Status | Notes |
|------|--------|-------|
| PM2 online + restarts | PASS | `ai-interview-bot-backend` online; restart history present (autorestart enabled by PM2 default) |
| nginx branded 502/503/504 | FIXED | `error_page` → `/unavailable.html`; `frontend/public/unavailable.html` |
| HTTPS / health | PASS | `/health` → ok on live host |

---

## Paid-tier / infra leftovers (out of scope)

- **Redis (or similar)** for multi-worker live room sync and room survival across process restart  
- **LiveKit / Twilio** for in-app video (Meet/Zoom link remains MVP)  
- **SSO / semantic ATS / SEB lockdown** — not free-tier, not in this pass  
- **Multi-AZ HA** — single EC2 remains the free-tier topology  

---

## How to re-verify manually

1. Hard-refresh https://ai-interview-bot.duckdns.org  
2. Auth: wrong password + forgot password  
3. Apply with empty/corrupt PDF  
4. Generate assessment when Groq is slow (or with bad key briefly) — expect clear error, no stuck spinner  
5. Invite: deny camera; refresh mid-interview  
6. Live: open two tabs, kill network briefly — reconnect banner  
7. Privacy page: export while logged in  
8. `crontab -l` on EC2 for retention job  
