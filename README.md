# SmartSkale InterviewBot

## What Is This?
An AI-powered proctored interview platform.
Candidates take technical interviews with webcam 
monitoring. Recruiters create assessments, review 
results, and download reports.

Two ways to take an interview:
1. Mock Interview - candidate practices on their own
2. Recruiter Invite - company sends a link to candidate

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
- AI generates personalized questions (OpenAI GPT-4o)
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
| Database | SQLite → PostgreSQL ready | Simple deploy |
| ORM | SQLAlchemy 2.0 async | No raw SQL |
| Migrations | Alembic | Schema versioning |
| Auth | JWT + bcrypt | Secure, stateless |
| Question Gen | OpenAI GPT-4o | Best reasoning |
| Answer Judge | Groq Llama 3.1 | Fast + cheap |
| Transcription | OpenAI Whisper | Speech to text |
| Face Detection | MediaPipe | Local, no cloud |
| Identity Check | OpenCV | Face presence |
| PDF Reports | ReportLab | Pure Python |
| PDF Parsing | PyMuPDF | Resume + JD |
| Recording | WebM → MP4 (ffmpeg) | Universal playback |
| Email | Gmail SMTP | Free |
| Rate Limiting | SlowAPI | Brute force protection |

---

## How To Run Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- OpenAI API key (platform.openai.com)
- Groq API key (console.groq.com - free)
- ffmpeg (recommended for MP4 conversion; WebM playback works without it)

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
git clone https://github.com/smartskale001/SmartSkale-InterviewBot.git
cd SmartSkale-InterviewBot
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys in .env
alembic upgrade head
python app/proctoring/download_model.py
uvicorn app.main:app --port 8080
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

With the backend running on port 8080:

```bash
python scripts/full_test.py
```

Covers auth, mock interview, proctoring, recruiter portal, invite flow, PDF reports, and recording upload/playback. Expected: **51/51 PASS**. Results are written to `test_results.txt`.

---

## Environment Variables

| Variable | Purpose | Example |
|---|---|---|
| OPENAI_API_KEY | Questions + Whisper | sk-... |
| GROQ_API_KEY | Answer judging | gsk-... |
| SECRET_KEY | JWT signing | random 32 chars |
| DATABASE_URL | Database | sqlite+aiosqlite:///./smartskale.db |
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

SQLite for development. One line change for production:

Development (.env)
```
DATABASE_URL=sqlite+aiosqlite:///./smartskale.db
```

Production (.env)
```
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
```

No code changes needed. SQLAlchemy ORM handles both.

---

## Deployment

Quick summary:
- Backend: Railway (Dockerfile included; install ffmpeg in image for MP4)
- Frontend: Vercel (set `VITE_API_URL` to Railway URL)
- Database: Railway volume at `/app/data` for SQLite, or Railway PostgreSQL

---

## AWS Deployment

Deploy on a single **Ubuntu EC2 t2.micro** (free tier) with nginx serving the React build and proxying API traffic to uvicorn behind PM2.

### Prerequisites

- EC2 instance: **Ubuntu 22.04+**, instance type **t2.micro** (or larger if proctoring feels slow)
- Security group inbound rules:
  - **22** (SSH)
  - **80** (HTTP — nginx)
  - **8080** (optional — only if you need direct backend access for debugging; production uses nginx on port 80)
- GitHub repo access (HTTPS clone URL)
- API keys: OpenAI, Groq, and a strong `SECRET_KEY`

### First-time setup

```bash
# On the EC2 instance (as a user with sudo):
git clone https://github.com/YOUR_ORG/YOUR_REPO.git /var/www/ai-interview-bot
cd /var/www/ai-interview-bot

# Edit deploy/setup.sh — set REPO_URL and BRANCH before running, or clone manually as above
chmod +x deploy/setup.sh
sudo ./deploy/setup.sh
```

After setup completes, **edit `/var/www/ai-interview-bot/.env`** with production values (see checklist below), then:

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

### What the deploy folder contains

| File | Purpose |
|---|---|
| `deploy/nginx.conf` | Serves `frontend/dist` on port 80; proxies `/api/`, `/health`, and `/proctor/` to `127.0.0.1:8080` |
| `deploy/ecosystem.config.js` | PM2 config — `uvicorn app.main:app --host 127.0.0.1 --port 8080 --workers 2` |
| `deploy/setup.sh` | One-time EC2 provisioning (apt, venv, build, nginx, PM2) |
| `deploy/deploy.sh` | Pull latest code, rebuild frontend, migrate, restart |

### Production `.env` checklist (EC2)

Paste these into `/var/www/ai-interview-bot/.env` after setup. **Required** keys will prevent startup if missing.

**Required**

| Variable | Example / notes |
|---|---|
| `SECRET_KEY` | `openssl rand -hex 32` |
| `DATABASE_URL` | `sqlite+aiosqlite:////var/www/ai-interview-bot/data/smartskale.db` (persistent path) |
| `OPENAI_API_KEY` | OpenAI key — questions + Whisper |
| `GROQ_API_KEY` | Groq key — answer judging |

**Production (strongly recommended)**

| Variable | Example / notes |
|---|---|
| `APP_ENV` | `production` |
| `FRONTEND_URL` | `http://<EC2_PUBLIC_IP>` or your domain |
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


