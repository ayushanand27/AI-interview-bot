# AI Interview Bot

AI-powered **proctored technical interviews** — candidates practice or take recruiter invite interviews; recruiters create assessments and review results.

**Repo:** https://github.com/ayushanand27/AI-interview-bot

## Live Demo

| | |
|---|---|
| **App (HTTPS)** | https://ai-interview-bot.duckdns.org |
| **Health** | https://ai-interview-bot.duckdns.org/health |
| **Recruiter** | https://ai-interview-bot.duckdns.org/recruiter |
| **Host** | AWS EC2 `t3.micro` (Ubuntu 24.04, Mumbai) + nginx + Let's Encrypt |
| **AI** | Groq (questions, judging, Whisper transcription) |

> Webcam / microphone need a **secure context** (`https://` or `localhost`). The live site uses free DuckDNS + Let's Encrypt SSL.

---

## What it does

1. **Mock interview** — candidate registers, uploads resume + JD, gets AI questions, takes a proctored interview, receives score + PDF report.
2. **Recruiter invite** — recruiter builds a JD-only assessment, shares a link; candidate verifies identity, interviews; recruiter reviews transcripts, integrity flags, recordings, and PDFs.

---

## Features

- Auth: register / login, email verify, forgot/reset password (Gmail SMTP)
- Candidate mock flow + recruiter portal (`/recruiter`)
- Invite flow with ID + selfie identity check
- Proctoring: face / multi-face / looking away / tab switch / virtual camera / extensions
- Human-review flag on suspicious sessions
- Assessment list / delete / copy invite
- Privacy policy page (`/privacy`)
- Interview recording (WebM → MP4 when ffmpeg available)
- Candidate + recruiter PDF reports

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
| FastAPI + Python | API, auth, interviews, reports |
| React + Vite + TypeScript | Candidate + recruiter UI |
| Postgres (local Docker) / SQLite (EC2) | Data |
| Groq | Questions, judging, transcription |
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

See `.env.example` and `.env.production.example`.

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
app/           FastAPI API, auth, interviews, proctoring, reports
frontend/      React + Vite UI
deploy/        EC2 / nginx / HTTPS scripts
alembic/       DB migrations
scripts/       bootstrap_db, full_test, dev helpers
```

---

## License / notes

Personal project — https://github.com/ayushanand27/AI-interview-bot  
Do not commit `.env` or API keys. Use Gmail **App Passwords** only for SMTP.
