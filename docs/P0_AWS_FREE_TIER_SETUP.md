# P0 — AWS Free Tier setup (Mumbai / `ap-south-1`)

You do the AWS Console steps below. The app already supports **optional S3**,
**retention cleanup**, **DSAR export/delete**, and **Postgres** without wiping
production SQLite until you confirm RDS is ready.

**Preferred region:** `ap-south-1` (Mumbai) — same region as the existing EC2
instance at `13.207.191.193` / `/var/www/ai-interview-bot`.

When finished, reply in chat with:

> RDS + S3 ready. Paste these into EC2 `.env` (or paste values here for cutover):
> `DATABASE_URL=...`
> `S3_BUCKET=...`
> `AWS_ACCESS_KEY_ID=...`
> `AWS_SECRET_ACCESS_KEY=...`
> `AWS_REGION=ap-south-1`

Do **not** delete the SQLite file. Cutover will only switch `DATABASE_URL` after
you confirm.

---

## Checklist A — RDS PostgreSQL (free tier)

1. Open **AWS Console → RDS → Create database**.
2. Choose **Standard create** → Engine **PostgreSQL** (16.x if available).
3. Templates: **Free tier** (if shown). Otherwise pick:
   - Instance: `db.t3.micro` or `db.t4g.micro`
   - Storage: **gp2/gp3**, **20 GB**, **no storage autoscaling** (or cap low)
   - **Single-AZ** (not Multi-AZ)
4. DB identifier: e.g. `smartskale-interview-db`
5. Master username / password: choose strong values; **save them**.
6. Initial database name: `interview_bot`
7. Connectivity:
   - VPC: **same VPC as your EC2**
   - Public access: **No** (preferred)
   - VPC security group: create new, e.g. `smartskale-rds-sg`
8. After create, edit **smartskale-rds-sg** inbound rules:
   - Type: **PostgreSQL** / port **5432**
   - Source: **the EC2 instance security group** (not `0.0.0.0/0`)
9. Wait until Status = **Available**. Copy the **Endpoint** hostname.

**EC2 `.env` value (after bootstrap):**

```env
DATABASE_URL=postgresql+asyncpg://MASTER_USER:MASTER_PASSWORD@RDS_ENDPOINT:5432/interview_bot
```

URL-encode special characters in the password if needed (`@`, `#`, etc.).

**Do not change production `DATABASE_URL` yet** until you tell the agent RDS is ready.
Keep the current SQLite URL until cutover:

```env
DATABASE_URL=sqlite+aiosqlite:////var/www/ai-interview-bot/data/interview_bot.db
```

**Optional local/dev alternatives (already supported):**

- Docker Postgres: `docker compose up -d` →  
  `DATABASE_URL=postgresql+asyncpg://interview:interview@127.0.0.1:5433/interview_bot`
- SQLite: `DATABASE_URL=sqlite+aiosqlite:///./interview_bot.db`

---

## Checklist B — S3 bucket + IAM

1. **S3 → Create bucket**
   - Name: e.g. `smartskale-interview-artifacts-<your-unique-suffix>`
   - Region: **ap-south-1**
   - Block all public access: **ON**
   - Default encryption: **SSE-S3** (AES-256) is fine
2. **IAM → Users → Create user** (programmatic access), e.g. `smartskale-s3-uploader`
3. Attach an **inline policy** (replace bucket name):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ObjectRW",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
    },
    {
      "Sid": "ListBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:HeadBucket"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME"
    }
  ]
}
```

4. Create **Access key** for the user → save Access key ID + Secret.

**EC2 `.env` values:**

```env
S3_BUCKET=YOUR_BUCKET_NAME
S3_PREFIX=interview-bot
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1
```

If these are unset, the app keeps using local `UPLOAD_DIR` (backward compatible).

---

## Checklist C — Retention days (optional)

```env
ARTIFACT_RETENTION_DAYS=90
IDENTITY_RETENTION_DAYS=30
RECORDING_RETENTION_DAYS=60
```

Dry-run cleanup (safe):

```bash
cd /var/www/ai-interview-bot
source .venv/bin/activate
python scripts/cleanup_retention.py
```

Real delete (only when you intend to purge):

```bash
python scripts/cleanup_retention.py --execute
```

---

## Checklist D — Tell the agent when done

Paste into chat:

1. RDS endpoint + that SG only allows EC2 SG on 5432  
2. S3 bucket name + region  
3. Confirmation you added the env vars on EC2 **or** paste them here (agent will apply carefully)  
4. Explicit OK to switch `DATABASE_URL` (this is the only destructive cutover step)

The agent will then:

1. Point `DATABASE_URL` at RDS  
2. Run `python scripts/bootstrap_db.py` (create schema / alembic)  
3. Restart PM2  
4. Run `scripts/live_deploy_test.py`  
5. Leave SQLite file untouched as backup  

Optional data copy (risky on free tier — usually skip and start fresh):

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-url 'sqlite:////var/www/ai-interview-bot/data/interview_bot.db' \
  --postgres-url 'postgresql+psycopg2://USER:PASS@RDS:5432/interview_bot' \
  --dry-run
```

---

## What the agent already shipped (no AWS action required)

- S3-aware object storage with local fallback  
- Retention dry-run / execute script  
- DSAR APIs: `/api/v1/privacy/export`, `/delete-request`, recruiter admin variants  
- `pytesseract` + `tesseract-ocr` install on deploy  
- Postgres pool hardening + docker-compose Postgres for EC2/dev if RDS not ready  

**Phased features 1–5 stay intact** — none of the above requires wiping the live DB.

---

## Retention cleanup cron (EC2)

`scripts/cleanup_retention.py` should run daily so artifacts / identity / recordings
respect `ARTIFACT_RETENTION_DAYS`, `IDENTITY_RETENTION_DAYS`, and
`RECORDING_RETENTION_DAYS` from `.env`.

Dry-run once:

```bash
cd /var/www/ai-interview-bot
source .venv/bin/activate
python scripts/cleanup_retention.py
```

Install (ubuntu user crontab, 03:00 UTC):

```cron
0 3 * * * cd /var/www/ai-interview-bot && .venv/bin/python scripts/cleanup_retention.py --execute >> /var/www/ai-interview-bot/logs/retention_cleanup.log 2>&1
```

Ensure `logs/` exists (`mkdir -p /var/www/ai-interview-bot/logs`). Do not put secrets in the cron line — the script loads `.env` from the app root.

---

## Coding sandbox (Judge0 RapidAPI free)

Demo / pitch coding rounds use **Judge0 CE** via RapidAPI free (~500 runs/day, 1 concurrent). Candidate code never runs on the interview EC2.

1. Create a free RapidAPI account and subscribe to [Judge0 CE](https://rapidapi.com/judge0-official/api/judge0-ce) (Basic $0).
2. Copy your `X-RapidAPI-Key` into EC2 `.env`:

```bash
CODING_QUESTIONS_ENABLED=true
JUDGE0_RAPIDAPI_KEY=your-rapidapi-key
JUDGE0_RAPIDAPI_HOST=judge0-ce.p.rapidapi.com
```

3. Restart PM2. Confirm `/api/v1/status` shows `"coding_judge_configured": true`.
4. In recruiter UI, add a **Coding** question (or include `coding` in generate types). Candidate invite flow shows Monaco + Run public tests + Submit.

Supported languages: C, C++, Python, Perl, Java, JavaScript. Hidden tests grade on final submit; public tests are candidate-visible only.

