# Demo script — ATS shortlist + Live interview + Assessments

Use this walkthrough when showing the product. Free-tier demo mode (Meet/Zoom for video; SandboxAPI coding quota).

## 1. Recruiter login

1. Open https://ai-interview-bot.duckdns.org/recruiter
2. Log in as recruiter → dashboard

## 2. Jobs + ATS shortlist

1. In **Jobs · ATS shortlist · Live interview**:
   - Title: e.g. `Backend Engineer`
   - Paste a JD that mentions Python, FastAPI, AWS, Docker, etc.
2. Click **Create job + apply link** → Copy the `/apply/{token}` URL
3. Open the apply link (incognito / second browser):
   - Enter name + email
   - Upload a resume PDF/DOCX
4. Candidate sees ATS score + matched / missing skills
5. Back on recruiter dashboard → **View** job → applicants ranked by score
6. Click **Shortlist** on a strong resume
7. Click **Live interview** on that row (opens shared room; paste Meet URL first if you want video)

## 3. Live interview room

1. Recruiter: room opens with `?role=recruiter`
2. Share candidate link: `/live/{token}?role=candidate`
3. Optional: open the Meet/Zoom URL shown at the top for video/audio
4. Both see the same Monaco editor (edits sync over WebSocket)
5. Click **Run public tests** (uses SandboxAPI — demo quota)
6. Use chat for HR notes; recruiter can **End room**

## 4. Async assessment (existing)

1. **New assessment** → JD → Generate questions (Library-first) → Create invite
2. Candidate takes `/interview/invite/{token}` alone (identity + proctoring)
3. Recruiter reviews score, report, recording under Interviews

## Positioning for demos

| Capability | How we demo it |
|---|---|
| Sourcing / ATS | Jobs apply link + score shortlist |
| Live tech/HR | Shared editor + Meet link |
| Take-home screen | Assessment invite flow |

When customers pay: enable semantic ATS (`ATS_ENABLE_SEMANTIC`), paid judge quota, and in-app WebRTC (LiveKit/Twilio).
