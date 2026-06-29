# SmartSkale InterviewBot

## Live Demo

**URL:** http://13.207.191.193

Hosted on **AWS EC2 free tier** (t3.micro, Mumbai region). The frontend, API, and proctoring endpoints are served from a single instance via nginx.

Question generation, judging, and transcription run on **Groq** (configure `GROQ_API_KEY` in `.env`).

---

## What Is This?
An AI-powered proctored interview platform.
Candidates take technical interviews with webcam 
monitoring. Recruiters create assessments, review 
results, and download reports.

Two ways to take an interview:
1. Mock Interview - candidate practices on their own
2. Recruiter Invite - company sends a link to candidate

---

## Architecture

Production runs on a single **AWS EC2** instance (Ubuntu 24.04, t3.micro free tier, Mumbai region):

```
Browser → nginx (:80)
            ├── /              → React/Vite static build (frontend/dist)
            ├── /api/          → FastAPI backend (127.0.0.1:8080)
            ├── /health        → backend health check
            └── /proctor/      → proctoring sub-app (face/object detection)

PM2 → uvicorn app.main:app --host 127.0.0.1 --port 8080 --workers 1
```

| Component | Role |
|---|---|
| **FastAPI backend** (Python) | REST API, auth, interviews, recruiter portal, reports |
| **React + TypeScript frontend** | Candidate and recruiter UIs (Vite build) |
| **PostgreSQL / SQLite + SQLAlchemy + Alembic** | Database (Postgres locally via Docker; SQLite on EC2) |
| **Groq API** | Question generation, answer evaluation, recruiter assessments, Whisper transcription |
| **OpenAI API** | Optional legacy fallback (not required) |
| **nginx** | Reverse proxy — serves frontend, proxies `/api/`, `/health`, `/proctor/` |
| **PM2** | Process manager — keeps uvicorn running with auto-restart |
| **Proctoring** | MediaPipe (face/pose), YOLOv8n (prohibited-object detection), OpenCV |

Local development uses the same stack without nginx/PM2: Vite dev server on port 5173 and uvicorn on port 8080.

---

## Two Interview Modes

### Mode 1 — Mock Interview (Self Practice)
- Candidate registers and logs in
- Uploads resume PDF
- Pastes JD text OR uploads JD as PDF
- AI generates personalized questions from resume + JD
- Takes proctored interview (webcam monitored)
- Gets score, recording, and personal feedback report

### Mode 2 — Recruiter Assigned Interview
- Recruiter creates assessment from JD only
- Pastes JD text OR uploads JD as PDF
- AI generates questions from JD only (unbiased)
- Recruiter shares unique invite link with candidate
- Candidate opens link, enters details, verifies identity
- Takes proctored interview
- Gets score, recording, and personal feedback report
- Recruiter sees all results, full reports, recordings

---

## Complete Feature List

### Authentication
- Candidate and Recruiter separate accounts
- Email + password registration
- Email verification (link sent to inbox)
- Forgot password / reset password via email
- JWT tokens (access + refresh)
- Role-based access control

### Mock Interview Flow
- Resume PDF upload
- JD input: paste text OR upload PDF (both options)
- AI generates personalized questions (Groq Llama 3.1)
- One question at a time (like real interview)
- Text answer OR audio answer (mic recording)
- AI judges each answer (Groq Llama 3.1)
- Real-time proctoring throughout

### Recruiter Portal (/recruiter)
- Separate recruiter login/register
- JD input: paste text OR upload PDF
- Configure: question count, difficulty, expiry
- Generate unique invite link per assessment
- Dashboard: see all candidate results
- View full transcripts and scores
- Download detailed PDF reports
- Watch candidate recordings

### Invite Link Flow
- Candidate opens unique link
- Enters name, email, phone
- Uploads government ID photo
- Takes live selfie for verification
- Identity verified before interview starts
- Takes interview (same questions for all candidates)
- Gets personal report and recording

### Proctoring System
- Face presence detection (no face = flag)
- Multiple faces detection (help = flag)
- Head pose monitoring (looking away = flag)
- Tab switching detection
- Screen recording extension detection
- Virtual camera detection
- Pre-interview checklist (camera, fullscreen, extensions)
- Score penalty system: 2% to 30% per violation
- Maximum 50% total penalty
- Interview never terminated automatically
- Full violation timeline in recruiter report
- Why not iris tracking: unreliable on webcams + 
  DPDP Act 2023 legal risk (biometric data)

### Scoring System
- 4 criteria: Technical(40%), Completeness(25%), 
  Communication(20%), Depth(15%)
- Integrity penalty applied to raw score
- Final recommendation: Strong Hire / Hire / Maybe / No Hire
- Candidate sees: performance level (not hire decision)
- Recruiter sees: full details including hire decision

### Interview Recording
- Full webcam + audio recorded during interview (WebM in browser)
- Auto-converted to MP4 via ffmpeg when available
- Graceful WebM fallback if ffmpeg is missing or conversion fails
- Candidate can watch own recording after interview
- Recruiter can watch any candidate recording
- Playback serves MP4 first, then WebM (Chrome/Firefox)
- Recording access requires authentication

### Reports
- Candidate PDF: score, feedback, performance level
  (hire decision hidden from candidate)
- Recruiter PDF: full details, violations timeline,
  penalty breakdown, hire recommendation

### Email System
- Email verification on register
- Password reset via email
- Gmail SMTP (configure in .env)
- Falls back to terminal link if SMTP not configured

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Backend | FastAPI + Python | Async, auto docs |
| Frontend | React + Vite + TypeScript | Fast, typed |
| Database | PostgreSQL (local dev) / SQLite (EC2) — SQLAlchemy 2.0 async | Production-ready ORM; swap via `DATABASE_URL` |
| Migrations | Alembic | Schema versioning |
| Auth | JWT + bcrypt | Secure, stateless |
| Question Gen | Groq Llama 3.1 | Mock-interview questions |
| Recruiter Q Gen | Groq Llama 3.1 | JD-only assessment questions |
| Answer Judge | Groq Llama 3.1 | Fast + cheap scoring |
| Transcription | Groq Whisper | Speech to text |
| Face Detection | MediaPipe | Local, no cloud |
| Object Detection | YOLOv8n (Ultralytics) | Cell-phone / prohibited-object checks |
| Identity Check | OpenCV | Face presence |
| PDF Reports | ReportLab | Pure Python |
| PDF Parsing | PyMuPDF | Resume + JD |
| Recording | WebM → MP4 (ffmpeg) | Universal playback |
| Email | Gmail SMTP | Free |
| Rate Limiting | SlowAPI | Brute force protection |
| Production server | nginx + PM2 + uvicorn | EC2 deployment |
| Hosting | AWS EC2 (Ubuntu 24.04) | Free-tier t3.micro |

---

## How To Run Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- **Docker Desktop** (for local PostgreSQL — recommended)
- Groq API key (console.groq.com — free tier)
- ffmpeg (recommended for MP4 conversion; WebM playback works without it)

> **Note:** OpenAI is optional. All AI features (questions, judging, transcription) use Groq when `GROQ_API_KEY` is set.

### Database (PostgreSQL — recommended for local dev)

Local development uses **PostgreSQL in Docker** on port **5433** (avoids conflict with a system Postgres on 5432).

**Windows**
```powershell
# From project root
.\scripts\dev_db_postgres.ps1
```

**macOS / Linux**
```bash
docker compose up -d postgres
# Wait until healthy, then:
python scripts/bootstrap_db.py
```

Set in `.env` (single line — no duplicate `DATABASE_URL`):
```
DATABASE_URL=postgresql+asyncpg://interview:interview@127.0.0.1:5433/interview_bot
```

**Troubleshooting**
- `Docker is required` in Cursor terminal → open a **new** PowerShell window after installing Docker Desktop, or run the script from Windows Terminal.
- `password authentication failed` on port 5432 → you are hitting the wrong Postgres; use port **5433** as above.
- Windows **User** environment variable `DATABASE_URL` overrides `.env` — remove it or set it to the same `5433` URL.

**SQLite fallback** (no Docker): use `DATABASE_URL=sqlite+aiosqlite:///./smartskale.db` in `.env` and run `python scripts/bootstrap_db.py`.

### Install ffmpeg (for MP4 recording conversion)

**Windows**
```bash
winget install ffmpeg
# or: choco install ffmpeg
ffmpeg -version
```

**macOS**
```bash
brew install ffmpeg
```

**Linux**
```bash
sudo apt install ffmpeg
```

If ffmpeg is not installed, recordings are still saved and played back as WebM.

### Backend Setup
```bash
git clone https://github.com/ayushanand27/AI-interview-bot.git
cd AI-interview-bot
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in GROQ_API_KEY and DATABASE_URL in .env

# Start Postgres + create tables (see Database section above)
# Windows: .\scripts\dev_db_postgres.ps1
# macOS/Linux: docker compose up -d postgres && python scripts/bootstrap_db.py

python app/proctoring/download_model.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Access
- Candidate portal: http://localhost:5173
- Recruiter portal: http://localhost:5173/recruiter
- API docs (Swagger): http://127.0.0.1:8080/docs

### Run Full Test Suite

With the backend running on port 8080 and Postgres (or SQLite) configured:

```bash
python scripts/full_test.py
```

Covers auth, mock interview, proctoring, recruiter portal, invite flow, PDF reports, and recording upload/playback. Expected: **56/56 PASS**. Results are written to `test_results.txt`.

Live EC2 smoke test (optional):

```bash
python scripts/live_deploy_test.py
```

---

## Environment Variables

| Variable | Purpose | Example |
|---|---|---|
| GROQ_API_KEY | Questions, judging, Whisper transcription | gsk-... |
| GROQ_MODEL | Question + judge model | llama-3.1-8b-instant |
| GROQ_WHISPER_MODEL | Audio transcription | whisper-large-v3 |
| OPENAI_API_KEY | Optional legacy (not required with Groq) | sk-... |
| SECRET_KEY | JWT signing | random 32 chars |
| DATABASE_URL | Database connection | `postgresql+asyncpg://interview:interview@127.0.0.1:5433/interview_bot` (local Docker) or `sqlite+aiosqlite:///./smartskale.db` |
| ALLOWED_ORIGINS | Frontend URL | http://localhost:5173 |
| SMTP_EMAIL | Gmail for emails | you@gmail.com |
| SMTP_PASSWORD | Gmail App Password | 16 char app password |
| FRONTEND_URL | For email links | http://localhost:5173 |
| DEBUG | Dev mode | True |

### Gmail App Password Setup
1. Enable 2FA on Gmail account
2. Go to myaccount.google.com/apppasswords
3. Create app password for "SmartSkale"
4. Use the 16-character password in SMTP_PASSWORD

---

## API Reference
Full interactive docs: http://127.0.0.1:8080/docs

Key endpoint groups:
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- GET /api/v1/auth/verify-email?token=
- POST /api/v1/auth/forgot-password
- POST /api/v1/auth/reset-password
- POST /api/v1/interviews/sessions
- POST /api/v1/interviews/sessions/{id}/questions
- GET /api/v1/interviews/sessions/{id}/current-question
- POST /api/v1/interviews/sessions/{id}/answers
- POST /api/v1/interviews/sessions/{id}/audio-answer
- POST /api/v1/interviews/sessions/{id}/end
- GET /api/v1/interviews/sessions/{id}/my-report
- GET /api/v1/interviews/sessions/{id}/my-recording
- GET /api/v1/recruiter/sessions
- GET /api/v1/recruiter/sessions/{id}/report
- POST /api/v1/recruiter/create-assessment
- GET /api/v1/invite/{token}
- POST /proctor/analyze
- GET /proctor/health

---

## Proctoring Design Decision

We use face presence, head pose, and tab switching
instead of iris/gaze tracking.

Why no iris tracking:
- Standard webcams give only 20x20 pixels of iris
- Causes 30-50% false alarms on innocent candidates
- Classified as biometric data under India DPDP Act 2023
- Legal risk: up to 250 crore penalty per instance

This is the same approach used by Mercer Mettl, 
iMocha, and Talview in production.

---

## Database

The app supports **PostgreSQL** and **SQLite** via a single `DATABASE_URL` — no code changes when switching.

### Local development (PostgreSQL — recommended)

Uses `docker-compose.yml` (Postgres 16 on host port **5433**):

| Item | Value |
|---|---|
| User / password | `interview` / `interview` |
| Database | `interview_bot` |
| URL | `postgresql+asyncpg://interview:interview@127.0.0.1:5433/interview_bot` |

Bootstrap (creates ORM tables + aligns Alembic):

```bash
# Windows
.\scripts\dev_db_postgres.ps1

# macOS / Linux
docker compose up -d postgres
python scripts/bootstrap_db.py
```

### Production (EC2 — SQLite default)

SQLite keeps the free-tier instance simple (no extra DB server):

```
DATABASE_URL=sqlite+aiosqlite:////var/www/ai-interview-bot/data/smartskale.db
```

### Production (managed PostgreSQL)

When you add RDS, Supabase, or Railway Postgres:

```
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
```

Deploy runs `python scripts/bootstrap_db.py` (fresh DB: `create_all` + stamp; existing DB: `alembic upgrade head`).

---

## Deployment

**Production:** AWS EC2 (Ubuntu 24.04, t3.micro free tier, Mumbai) — see [Live Demo](#live-demo).

The `deploy/` folder contains scripts used for the live instance. Alternative hosting (Render via `Dockerfile` + `render.yaml`) is also supported but not the current production setup.

### First-time setup on EC2

```bash
# SSH into your EC2 instance, then:
git clone https://github.com/ayushanand27/AI-interview-bot.git /var/www/ai-interview-bot
cd /var/www/ai-interview-bot

chmod +x deploy/setup.sh
sudo ./deploy/setup.sh
```

`deploy/setup.sh` (run as root) will:

1. Update apt and install Python, nginx, Node.js 20, PM2, ffmpeg, and OpenCV libraries
2. Create a Python venv and `pip install -r requirements.txt`
3. Download proctoring models (`download_model.py`, YOLOv8n weights)
4. Build the frontend (`npm ci && npm run build` — leave `VITE_API_URL` unset for same-origin nginx)
5. Copy `deploy/nginx.conf` into `/etc/nginx/sites-available/` and enable the site
6. Run `python scripts/bootstrap_db.py` (schema + migrations)
7. Start the backend with PM2 (`deploy/ecosystem.config.js`)

After setup, **edit `/var/www/ai-interview-bot/.env`** with production values (see [Production `.env` checklist](#production-env-checklist-ec2) below), then:

```bash
pm2 restart ai-interview-bot-backend
sudo nginx -s reload
```

Open `http://<EC2_PUBLIC_IP>/` in a browser. Health check: `http://<EC2_PUBLIC_IP>/health`.

### Re-deploy after code changes

```bash
cd /var/www/ai-interview-bot
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

`deploy/deploy.sh` will:

1. Fix app directory ownership (`chown` if needed)
2. `git pull origin main`
3. `pip install -r requirements.txt` (inside `.venv`)
4. Rebuild the frontend (`npm ci && npm run build`)
5. `python scripts/bootstrap_db.py`
6. `pm2 restart ai-interview-bot-backend`
7. `sudo nginx -s reload`

### EC2 prerequisites

- Instance: **Ubuntu 24.04**, type **t3.micro** (free tier) or larger if proctoring feels slow
- Security group inbound: **22** (SSH), **80** (HTTP)
- **8080** optional — only for direct backend debugging; production traffic goes through nginx on port 80

### Deploy folder reference

| File | Purpose |
|---|---|
| `deploy/nginx.conf` | Serves `frontend/dist` on port 80; proxies `/api/`, `/health`, `/proctor/` to `127.0.0.1:8080` |
| `deploy/ecosystem.config.js` | PM2 — `uvicorn app.main:app --host 127.0.0.1 --port 8080 --workers 1`, auto-restart |
| `deploy/setup.sh` | One-time EC2 provisioning |
| `deploy/deploy.sh` | Pull, rebuild, bootstrap DB, restart |
| `docker-compose.yml` | Local Postgres only (not used on EC2) |
| `scripts/dev_db_postgres.ps1` | Windows: start Docker Postgres + bootstrap |
| `scripts/bootstrap_db.py` | Create tables / run Alembic (all environments) |

---

## AWS Deployment

Detailed EC2 checklist and environment variables for the live instance.

### Prerequisites

- EC2 instance: **Ubuntu 24.04**, type **t3.micro** (Mumbai / ap-south-1 free tier)
- Security group inbound rules:
  - **22** (SSH)
  - **80** (HTTP — nginx)
  - **8080** (optional — direct backend access for debugging only)
- GitHub repo: https://github.com/ayushanand27/AI-interview-bot (`main` branch)
- API keys: **Groq** (required), strong `SECRET_KEY`; OpenAI optional

### First-time setup

Same steps as [Deployment → First-time setup on EC2](#first-time-setup-on-ec2):

```bash
git clone https://github.com/ayushanand27/AI-interview-bot.git /var/www/ai-interview-bot
cd /var/www/ai-interview-bot
chmod +x deploy/setup.sh
sudo ./deploy/setup.sh
```

After setup completes, **edit `/var/www/ai-interview-bot/.env`** with production values, then:

```bash
pm2 restart ai-interview-bot-backend
sudo nginx -s reload
```

### Re-deploy after code changes

```bash
cd /var/www/ai-interview-bot
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

### Production `.env` checklist (EC2)

Paste these into `/var/www/ai-interview-bot/.env` after setup. Values match `.env.example`; **required** keys prevent startup if missing.

**Required** (from `.env.example`)

| Variable | Example / notes |
|---|---|
| `SECRET_KEY` | `openssl rand -hex 32` |
| `DATABASE_URL` | `sqlite+aiosqlite:////var/www/ai-interview-bot/data/smartskale.db` (persistent path on EC2) |
| `GROQ_API_KEY` | Groq key — questions, judging, transcription |
| `GROQ_MODEL` | e.g. `llama-3.1-8b-instant` |
| `GROQ_WHISPER_MODEL` | e.g. `whisper-large-v3` |
| `OPENAI_API_KEY` | Optional — not required when using Groq |
| `INTERVIEW_QUESTION_COUNT` | Default question count (e.g. `5`) |

**Production (strongly recommended on EC2)**

| Variable | Example / notes |
|---|---|
| `APP_ENV` | `production` |
| `FRONTEND_URL` | `http://13.207.191.193` or your domain |
| `ALLOWED_ORIGINS` | Same as `FRONTEND_URL` (comma-separated if multiple) |
| `UPLOAD_DIR` | `/var/www/ai-interview-bot/uploads` |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_EMAIL` | Gmail address for verification / reset emails |
| `SMTP_PASSWORD` | Gmail App Password (16 chars) |

**Optional (defaults exist in `app/core/config.py`)**

| Variable | Default |
|---|---|
| `DEBUG` | `False` |
| `OPENAI_MODEL` | `gpt-4o` |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` |
| `INTERVIEW_QUESTION_COUNT` | `5` |
| `MAX_ANSWER_LENGTH` | `2000` |
| `QUESTION_TIMER_SECONDS` | `180` |
| `SESSION_IDLE_TIMEOUT_MINUTES` | `15` |
| `MAX_FILE_SIZE_MB` | `10` |

**Frontend build (same-server nginx — usually leave unset)**

| Variable | Notes |
|---|---|
| `VITE_API_URL` | Leave **empty** so the browser uses relative `/api` and `/proctor` paths through nginx |
| `VITE_QUESTION_TIMER_SECONDS` | Optional override for UI timer (default `180`) |

---


