# AI Interview Bot

AI-powered hiring flow: **Jobs → ATS shortlist → Assessment invites → Live coding rooms**. Candidates take proctored async assessments or join collaborative live rooms; recruiters create mixed question-type assessments and review results.

**Repo:** https://github.com/ayushanand27/AI-interview-bot

## Live Demo

| | |
|---|---|
| **App (HTTPS)** | https://ai-interview-bot.duckdns.org |
| **Health** | https://ai-interview-bot.duckdns.org/health |
| **Recruiter** | https://ai-interview-bot.duckdns.org/recruiter |
| **Host** | AWS EC2 `t3.micro` (Ubuntu 24.04, Mumbai) + nginx + Let's Encrypt |
| **Stack** | FastAPI + React (Vite) + SQLite (prod) / Postgres (local) + Groq |

> Webcam / microphone need a **secure context** (`https://` or `localhost`). The live site uses free DuckDNS + Let's Encrypt SSL.

### Quick demo path

1. Open https://ai-interview-bot.duckdns.org/recruiter → register / log in as recruiter  
2. **Jobs** — post a JD, share apply link; review ATS keyword shortlist  
3. **Assessments** — generate questions (subjective / MCQ / MSQ / numerical / coding), set max uses + optional exam duration, copy invite link  
4. Open the invite as a candidate (desktop Chrome/Edge) → identity check → proctored interview  
5. **Live** — create a collaborative coding room + Meet/Zoom URL (not proctored)

---

## What the product does

| Stage | What happens |
|---|---|
| **Jobs** | Recruiter posts a job; candidates apply with resume |
| **ATS** | Free-tier shortlist: resume structure hygiene + JD **keyword** match |
| **Assessment** | Recruiter builds a timed invite (mixed question types); candidate verifies identity and takes a **proctored** async interview |
| **Live** | Collaborative coding room + chat; video via **Google Meet / Zoom** link you provide |

Also: candidate **mock interview** (register → resume + JD → AI questions → proctored practice → score + PDF).

---

## Features (current)

- Auth: register / login, email verify, forgot/reset password (Gmail SMTP)
- Jobs + public apply + keyword ATS shortlist
- Recruiter assessments with editable question mix, per-question time/marks, **configurable invite max uses (1–100)**, optional **overall exam duration**
- Invite flow: welcome rules → details → ID + selfie liveness → preflight checklist → proctored room
- Question types: subjective, MCQ, MSQ, numerical, coding (Judge0 when configured)
- Browser proctoring signals (face, tab blur, fullscreen, audio, virtual cam heuristics, YOLO objects)
- Anti-cheat deterrents: copy-block, watermark, blur-on-blur, LLM paste canary
- Live collaborative coding rooms (WebSocket + Meet/Zoom link)
- Recruiter tenancy: list / extend / delete unused assessments; review own sessions, analytics, PDFs
- Privacy policy (`/privacy`), recording (WebM → MP4 when ffmpeg available)

---

## Explicit limitations / non-claims

This is a **demo-grade free-tier** product. Do **not** claim:

| Claim | Reality |
|---|---|
| Enterprise SSO / SAML / OIDC | **Not built** — email/password only |
| LiveKit / self-hosted WebRTC | **Not built** — live video is Meet/Zoom |
| Redis-backed multi-instance WS | **Not built** — single EC2 worker |
| Semantic / embedding ATS | **Not built** — keyword + structure only (`ATS_ENABLE_SEMANTIC=false`) |
| Org RBAC / multi-tenant admin | **Not built** — per-recruiter ownership |
| SEB / lockdown browser | **Not built** — browser SPA proctoring only |
| Dual-monitor / plagiarism ML | **Not built** |
| Live rooms are proctored | **They are not** — Meet handles video; honesty banner in-room |
| “Phones cannot see questions” / “ChatGPT-proof” | Deterrents only — not cryptographic guarantees |

Browser proctoring logs evidence for recruiters; it is **not** Safe Exam Browser or a locked OS.

---

## Free-tier roadmap (when paid infra is available)

| When you can pay for… | Then add… |
|---|---|
| Extra RAM / GPU or managed vectors | Semantic ATS (MiniLM / embeddings) |
| Dedicated media servers | LiveKit (or similar) in-app video |
| Multi-instance hosting | Redis-backed WebSocket pub/sub |
| IdP contract | SSO / org RBAC |

Until then, keep the demo on **t3.micro** + DuckDNS + optional free-tier RDS/S3 (see AWS docs below).

---

## Question types

Recruiters choose which kinds to generate and can edit each question before creating the invite:

| Type | Candidate UI | Scoring |
|---|---|---|
| **Subjective** (open-ended) | Textarea + optional audio | LLM judge (Groq) |
| **MCQ** (single correct) | Radio options (shuffled) | Exact match server-side |
| **MSQ** (multi-select) | Checkboxes (shuffled) | Exact set match server-side |
| **Numerical** | Number input | Exact / tolerance match server-side |
| **Coding** | Monaco editor + public tests | Judge0 hidden tests when configured |

- Per-question **time (seconds)** and **marks** are editable; optional **overall exam minutes** countdown on invite sessions.
- Correct keys stay on the invite JSON and are **never** sent to the candidate API response.
- Existing subjective-only invites keep working (default type = `subjective`).

---

## Proctoring (async assessments)

Logged / enforced during the interview room:

- Face missing / multiple faces / looking away (MediaPipe)
- Tab switch / window blur (focus-loss)
- Fullscreen exit
- Loud ambient audio
- Virtual camera / screen-recording extension heuristics
- Phone / prohibited object detection (YOLOv8n)
- Integrity penalty applied to final score; human-review flag for recruiters

**Live collaborative rooms** show an honesty banner and are **not** proctored.

---

## Anti-cheat (best-effort, browser SPA)

Implemented deterrents (aligned with industry practice, not absolute locks):

| Control | Behavior |
|---|---|
| **Copy / paste / cut block** | Clipboard events + Ctrl/Cmd+C/V/X blocked in the interview room; right-click disabled |
| **Dynamic watermark** | Candidate email/id + session id + timestamp tiled over the question pane |
| **Blur-on-blur** | Question text obscured when the window loses focus / tab is hidden |
| **LLM paste canary** | Low-visibility instructional canary + confidential footer |

### Honest limitations

- A **physical phone camera** pointed at the screen cannot be fully blocked in a browser SPA.
- Motivated candidates can retype questions, strip canaries, or use out-of-band AI tools.
- Copy-block, watermark, blur, and canaries are **deterrents + evidence aids**, not cryptographic guarantees.

---

## Architecture (production)

```
Browser → nginx (:443 HTTPS / :80 → redirect)
            ├── /           → React build (frontend/dist)
            ├── /api/       → FastAPI (127.0.0.1:8080)
            ├── /health
            └── /proctor/   → proctoring sub-app

PM2 → uvicorn app.main:app --host 127.0.0.1 --port 8080 --workers 1
```

| Piece | Role |
|---|---|
| FastAPI + Python | API, auth, interviews, objective grading, reports |
| React + Vite + TypeScript | Candidate + recruiter UI |
| Postgres (local Docker) / SQLite (EC2) | Data |
| Groq | Questions, subjective judging, Whisper transcription |
| MediaPipe + YOLOv8n + OpenCV | Proctoring / identity |
| nginx + PM2 | Reverse proxy + process manager |

---

## Local development

### Prerequisites

- Python 3.11+, Node 18+, Docker Desktop (Postgres), Groq API key
- ffmpeg optional (MP4 conversion)

### Database

```powershell
# Windows — Postgres on port 5433
.\scripts\dev_db_postgres.ps1
```

```bash
# macOS / Linux
docker compose up -d postgres
python scripts/bootstrap_db.py
```

`.env`:
```
DATABASE_URL=postgresql+asyncpg://interview:interview@127.0.0.1:5433/interview_bot
FRONTEND_URL=http://127.0.0.1:5173
ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

SQLite fallback: `DATABASE_URL=sqlite+aiosqlite:///./interview_bot.db`

### Backend

```bash
git clone https://github.com/ayushanand27/AI-interview-bot.git
cd AI-interview-bot
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
cp .env.example .env
# Set GROQ_API_KEY, SECRET_KEY, DATABASE_URL, SMTP_* in .env

python app/proctoring/download_model.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

### Frontend

```bash
cd frontend
npm install
npm run build   # must pass before deploy
npm run dev
```

Open **http://127.0.0.1:5173** (prefer `127.0.0.1` over LAN IP for camera).

- Recruiter: http://127.0.0.1:5173/recruiter  
- API docs: http://127.0.0.1:8080/docs  

### Tests

```bash
python scripts/full_test.py
```

---

## Environment variables

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Questions, judging, Whisper |
| `GROQ_MODEL` | e.g. `llama-3.1-8b-instant` |
| `GROQ_WHISPER_MODEL` | e.g. `whisper-large-v3` |
| `SECRET_KEY` | JWT signing |
| `DATABASE_URL` | Postgres or SQLite URL |
| `FRONTEND_URL` | Base URL for email links |
| `ALLOWED_ORIGINS` | CORS origins |
| `SMTP_EMAIL` / `SMTP_PASSWORD` | Gmail + **App Password** (not normal password) |
| `APP_ENV` | `development` / `production` |
| `UPLOAD_DIR` | Uploads path |
| `S3_BUCKET` / `AWS_*` | Optional S3 object storage |
| `ATS_ENABLE_SEMANTIC` | Keep `false` on free tier (keyword ATS only) |
| `ARTIFACT_RETENTION_DAYS` / `IDENTITY_RETENTION_DAYS` / `RECORDING_RETENTION_DAYS` | Cleanup TTLs |

See `.env.example` and `.env.production.example`.

**AWS free-tier P0 checklist (RDS + S3):** [`docs/P0_AWS_FREE_TIER_SETUP.md`](docs/P0_AWS_FREE_TIER_SETUP.md)

**Gmail App Password:** enable 2FA → [App passwords](https://myaccount.google.com/apppasswords) → put 16-char value in `SMTP_PASSWORD`.

---

## AWS EC2 deployment

### One-command update (after first setup)

```bash
cd /var/www/ai-interview-bot
bash deploy/go.sh
```

Optional env patch + deploy:

```bash
bash deploy/go.sh \
  --smtp-email you@gmail.com \
  --smtp-password 'your16charapppassword' \
  --frontend-url https://ai-interview-bot.duckdns.org
```

### HTTPS / webcam (DuckDNS or any domain)

1. Point DNS **A record** (or DuckDNS) to the EC2 public IP  
2. Security group: **22**, **80**, **443** open  
3. On the server:

```bash
bash deploy/setup_https.sh ai-interview-bot.duckdns.org you@gmail.com
```

This installs Certbot, configures nginx SSL, and sets `FRONTEND_URL` / `ALLOWED_ORIGINS` to `https://…`.

### First-time server install

```bash
git clone https://github.com/ayushanand27/AI-interview-bot.git /var/www/ai-interview-bot
cd /var/www/ai-interview-bot
chmod +x deploy/setup.sh
sudo ./deploy/setup.sh
# then edit .env, then:
bash deploy/go.sh --frontend-url https://YOUR_DOMAIN --smtp-email ... --smtp-password ...
bash deploy/setup_https.sh YOUR_DOMAIN you@gmail.com
```

### Deploy scripts

| File | Purpose |
|---|---|
| `deploy/go.sh` | Patch `.env` (optional) + full redeploy |
| `deploy/deploy.sh` | Pull `main`, build frontend, migrate, PM2 + nginx |
| `deploy/setup_https.sh` | Let's Encrypt HTTPS (DuckDNS-friendly, no `www` required) |
| `deploy/patch_production_env.sh` | Update SMTP / FRONTEND_URL on server |
| `deploy/setup.sh` | One-time EC2 provisioning |
| `deploy/nginx.conf` | Baseline HTTP nginx site |
| `deploy/ecosystem.config.js` | PM2 process config |

### Production `.env` (EC2 example)

```env
APP_ENV=production
SECRET_KEY=long-random-hex
DATABASE_URL=sqlite+aiosqlite:////var/www/ai-interview-bot/data/interview_bot.db
GROQ_API_KEY=gsk-...
FRONTEND_URL=https://ai-interview-bot.duckdns.org
ALLOWED_ORIGINS=https://ai-interview-bot.duckdns.org
UPLOAD_DIR=/var/www/ai-interview-bot/uploads
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=you@gmail.com
SMTP_PASSWORD=your-app-password
ATS_ENABLE_SEMANTIC=false
```

Leave `VITE_API_URL` empty for same-origin nginx.

### Security group

| Port | Why |
|---|---|
| 22 | SSH |
| 80 | HTTP (Certbot / redirect) |
| 443 | HTTPS (app + webcam) |

---

## Other hosting

- **Render:** `Dockerfile` + `render.yaml` (paid Docker instance recommended for OpenCV/YOLO)
- Local Docker Postgres: `docker-compose.yml`

---

## Project layout

```
app/           FastAPI API, auth, interviews, proctoring, reports, jobs/ATS, live rooms
frontend/      React + Vite UI
deploy/        EC2 / nginx / HTTPS scripts
alembic/       DB migrations
scripts/       bootstrap_db, full_test, dev helpers
docs/          AWS free-tier setup and ops notes
```

Question-type fields live in invite `questions_json` (JSON) — no DB column migration required for MCQ/MSQ/numerical metadata. Invite `duration_minutes` and session `interview_started_at` use Alembic migration `0022`.

---

## License / notes

Personal project — https://github.com/ayushanand27/AI-interview-bot  
Do not commit `.env` or API keys. Use Gmail **App Passwords** only for SMTP.
