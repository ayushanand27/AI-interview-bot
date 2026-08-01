# Coding judge (free-tier) — SandboxAPI + Piston

Keep coding **Run tests** reliable on a **t3.micro** without running heavy Judge0 on the box.

## Backends

| Backend | Env | Notes |
|---------|-----|--------|
| **SandboxAPI** (RapidAPI Basic free) | `CODING_RAPIDAPI_KEY` | Preferred when you have a key; monthly quota risk on demo day |
| **Piston** (public EMKC or self-hosted) | `CODING_PISTON_URL` optional | Lightweight; public URL used when empty + `auto`/`piston` |
| **auto** (default) | `CODING_JUDGE_BACKEND=auto` | Try SandboxAPI if keyed, else Piston; fall back on quota/auth outages |

## `.env` keys

```bash
CODING_QUESTIONS_ENABLED=true
CODING_JUDGE_BACKEND=auto          # auto | sandboxapi | piston
CODING_RAPIDAPI_KEY=               # RapidAPI SandboxAPI Basic free key (optional if using Piston)
CODING_JUDGE_HOST=sandboxapi.p.rapidapi.com
# Empty = public https://emkc.org/api/v2/piston
# Self-host example:
# CODING_PISTON_URL=http://127.0.0.1:2000/api/v2
CODING_PISTON_URL=
```

Check live config: `GET /api/v1/status` → `coding_judge_configured`, `coding_judge_backend`.

## Demo-day recommendation (EC2 t3.micro)

1. Keep RapidAPI SandboxAPI key if you have quota left.
2. Leave `CODING_JUDGE_BACKEND=auto` so Piston covers quota/auth failures.
3. **Do not** install full Judge0 on t3.micro (RAM/CPU).
4. Optional self-hosted Piston only if public EMKC is rate-limited — use a **small** install and few runtimes (python/js first). Expect memory pressure; prefer public Piston on micro instances.

### Optional self-hosted Piston (advanced)

```bash
# On EC2 — only if you accept extra RAM use
sudo docker pull ghcr.io/engineer-man/piston
# Follow upstream Piston docs to expose API on :2000 and install packages.
# Then in /var/www/ai-interview-bot/.env:
# CODING_JUDGE_BACKEND=piston
# CODING_PISTON_URL=http://127.0.0.1:2000/api/v2
pm2 restart ai-interview-bot-backend
```

After env changes: `pm2 restart ai-interview-bot-backend --update-env`.

## What stays working

- Assessment coding questions (public Run tests + hidden grading)
- Live interview room Run tests (same `run_test_cases` path)

Perl remains UI-listed but not executable on free backends (use Python / JS / Java / C / C++ for demos).
