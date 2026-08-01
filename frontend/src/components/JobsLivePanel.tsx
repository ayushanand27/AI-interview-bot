import { useEffect, useState } from "react";
import { jobsLiveApi, recruiterApi } from "../api/client";
import type { AssessmentSummary } from "../types/assessment";

type JobRow = {
  token: string;
  title: string;
  apply_link: string;
  created_at: string;
  application_count: number;
};

type AppRow = {
  id: number;
  full_name: string;
  email: string;
  ats_score: number;
  fit_label?: string | null;
  matched_skills: string[];
  missing_skills: string[];
  status: string;
  created_at: string;
};

type LiveRow = {
  token: string;
  title: string;
  meet_url: string | null;
  join_link: string;
  status: string;
  created_at: string;
};

interface JobsLivePanelProps {
  onError: (msg: string | null) => void;
  absoluteLink: (path: string) => string;
}

function parseEmails(raw: string): string[] {
  return raw
    .split(/[\s,;]+/)
    .map((e) => e.trim())
    .filter(Boolean);
}

export default function JobsLivePanel({
  onError,
  absoluteLink,
}: JobsLivePanelProps) {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [apps, setApps] = useState<AppRow[]>([]);
  const [jobTitle, setJobTitle] = useState("");
  const [jobJd, setJobJd] = useState("");
  const [jdMode, setJdMode] = useState<"paste" | "upload">("paste");
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [parsingJd, setParsingJd] = useState(false);
  const [meetUrl, setMeetUrl] = useState("");
  const [liveTitle, setLiveTitle] = useState("Live technical interview");
  const [liveRooms, setLiveRooms] = useState<LiveRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [copyMsg, setCopyMsg] = useState<string | null>(null);
  const [inviteDeliveryNote, setInviteDeliveryNote] = useState<string | null>(
    null,
  );

  const [inviteRoomToken, setInviteRoomToken] = useState<string | null>(null);
  const [inviteEmails, setInviteEmails] = useState("");
  const [inviteMessage, setInviteMessage] = useState("");
  const [inviteCandidateName, setInviteCandidateName] = useState("");
  const [inviteSending, setInviteSending] = useState(false);
  const [inviteStatus, setInviteStatus] = useState<string | null>(null);

  // Assessment invite from shortlist
  const [assessments, setAssessments] = useState<AssessmentSummary[]>([]);
  const [assessApp, setAssessApp] = useState<AppRow | null>(null);
  const [assessMode, setAssessMode] = useState<"existing" | "from_job">(
    "existing",
  );
  const [assessToken, setAssessToken] = useState("");
  const [assessDifficulty, setAssessDifficulty] = useState("medium");
  const [assessQuestionCount, setAssessQuestionCount] = useState(5);
  const [assessExpiryHours, setAssessExpiryHours] = useState(48);
  const [assessNote, setAssessNote] = useState("");
  const [assessEmail, setAssessEmail] = useState("");
  const [assessBusy, setAssessBusy] = useState(false);
  const [assessStatus, setAssessStatus] = useState<string | null>(null);
  const [assessDeliveryNote, setAssessDeliveryNote] = useState<string | null>(
    null,
  );

  function refreshJobs() {
    jobsLiveApi
      .listJobs()
      .then((res) => setJobs(res.data ?? []))
      .catch((err) =>
        onError(err instanceof Error ? err.message : "Failed to load jobs"),
      );
  }

  function refreshLive() {
    jobsLiveApi
      .listLiveRooms()
      .then((res) => setLiveRooms(res.data ?? []))
      .catch(() => {
        /* ignore */
      });
  }

  function refreshAssessments() {
    recruiterApi
      .listAssessments()
      .then((res) => {
        const list = (res.data ?? []).filter((a) => !a.is_expired);
        setAssessments(list);
        if (!assessToken && list.length > 0) {
          setAssessToken(list[0].token);
        }
      })
      .catch(() => {
        /* ignore — panel still usable */
      });
  }

  useEffect(() => {
    refreshJobs();
    refreshLive();
    refreshAssessments();
  }, []);

  useEffect(() => {
    if (!selectedJob) {
      setApps([]);
      return;
    }
    jobsLiveApi
      .listApplications(selectedJob)
      .then((res) => setApps(res.data ?? []))
      .catch((err) =>
        onError(err instanceof Error ? err.message : "Failed to load applicants"),
      );
  }, [selectedJob]);

  function openInviteForm(opts: {
    token: string;
    email?: string;
    name?: string;
  }) {
    setInviteRoomToken(opts.token);
    setInviteEmails(opts.email || "");
    setInviteCandidateName(opts.name || "");
    setInviteMessage("");
    setInviteStatus(null);
    setAssessApp(null);
  }

  function openAssessmentInvite(app: AppRow) {
    setAssessApp(app);
    setAssessEmail(app.email);
    setAssessNote("");
    setAssessStatus(null);
    setAssessDeliveryNote(null);
    setInviteRoomToken(null);
    refreshAssessments();
    const active = assessments.filter((a) => !a.is_expired);
    if (active.length > 0) {
      setAssessMode("existing");
      setAssessToken(active[0].token);
    } else {
      setAssessMode("from_job");
    }
  }

  async function resolveJdText(): Promise<string> {
    if (jdMode === "upload") {
      if (!jdFile) {
        throw new Error("Upload a JD file (PDF, Word, or TXT).");
      }
      setParsingJd(true);
      try {
        const parsed = await recruiterApi.parseJdPdf(jdFile);
        const text = (parsed.data?.jd_text || "").trim();
        if (text.length < 20) {
          throw new Error("Could not extract enough text from the JD file.");
        }
        setJobJd(text);
        return text;
      } finally {
        setParsingJd(false);
      }
    }
    const text = jobJd.trim();
    if (text.length < 20) {
      throw new Error(
        "Paste a job description (at least 20 characters) or upload a file.",
      );
    }
    return text;
  }

  async function createJob() {
    setBusy(true);
    onError(null);
    try {
      const jdText = await resolveJdText();
      const res = await jobsLiveApi.createJob({
        title: jobTitle,
        jd_text: jdText,
      });
      setJobTitle("");
      setJobJd("");
      setJdFile(null);
      refreshJobs();
      setSelectedJob(res.data.token);
      setCopyMsg(absoluteLink(res.data.apply_link));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Create job failed");
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(id: number, status: string) {
    try {
      await jobsLiveApi.updateApplicationStatus(id, status);
      if (selectedJob) {
        const res = await jobsLiveApi.listApplications(selectedJob);
        setApps(res.data ?? []);
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function startLive(opts?: {
    applicationId?: number;
    candidateName?: string;
    candidateEmail?: string;
  }) {
    setBusy(true);
    onError(null);
    setInviteStatus(null);
    try {
      const res = await jobsLiveApi.createLiveRoom({
        title: opts?.candidateName
          ? `Live with ${opts.candidateName}`
          : liveTitle || "Live technical interview",
        meet_url: meetUrl || undefined,
        application_id: opts?.applicationId,
      });
      refreshLive();
      const link = absoluteLink(`${res.data.join_link}?role=candidate`);
      setCopyMsg(link);
      openInviteForm({
        token: res.data.token,
        email: opts?.candidateEmail,
        name: opts?.candidateName,
      });
      window.open(`${res.data.join_link}?role=recruiter`, "_blank");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Live room failed");
    } finally {
      setBusy(false);
    }
  }

  async function sendLiveInvite() {
    if (!inviteRoomToken) return;
    const emails = parseEmails(inviteEmails);
    if (!emails.length) {
      onError("Enter at least one candidate email.");
      return;
    }
    setInviteSending(true);
    onError(null);
    setInviteStatus(null);
    try {
      const res = await jobsLiveApi.sendInvites(inviteRoomToken, {
        emails,
        message: inviteMessage.trim() || undefined,
        candidate_name: inviteCandidateName.trim() || undefined,
      });
      const failed = res.data.failed || [];
      const parts = [`Sent ${res.data.sent} invite email(s).`];
      if (failed.length) {
        parts.push(`Failed (${failed.length}): ${failed.join(", ")}`);
      }
      parts.push(`Live link: ${absoluteLink(res.data.live_link)}`);
      setInviteStatus(parts.join(" "));
      setInviteDeliveryNote(res.data.delivery_note || null);
      setCopyMsg(absoluteLink(res.data.live_link));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not send invites");
    } finally {
      setInviteSending(false);
    }
  }

  async function sendAssessmentInvite() {
    if (!assessApp) return;
    const email = assessEmail.trim().toLowerCase();
    if (!email || !email.includes("@")) {
      onError("Enter a valid candidate email.");
      return;
    }
    if (!selectedJob && assessMode === "from_job") {
      onError("Select a job first to create an assessment from its JD.");
      return;
    }

    setAssessBusy(true);
    onError(null);
    setAssessStatus(null);
    setAssessDeliveryNote(null);

    try {
      let token = assessToken;

      if (assessMode === "from_job") {
        if (!selectedJob) {
          throw new Error("No job selected.");
        }
        const jobRes = await jobsLiveApi.getJob(selectedJob);
        const jdText = (jobRes.data.jd_text || "").trim();
        if (jdText.length < 20) {
          throw new Error("This job has no usable JD for assessment generation.");
        }
        const created = await recruiterApi.createAssessment({
          jd_text: jdText,
          question_count: assessQuestionCount,
          difficulty: assessDifficulty,
          expiry_hours: assessExpiryHours,
        });
        token = created.data.token;
        refreshAssessments();
        setAssessToken(token);
        setCopyMsg(absoluteLink(created.data.invite_link));
      } else if (!token) {
        throw new Error("Pick an existing assessment or create one from this job.");
      }

      if (assessApp.status !== "shortlisted") {
        await jobsLiveApi.updateApplicationStatus(assessApp.id, "shortlisted");
      }

      const res = await recruiterApi.sendAssessmentInvites(token, {
        emails: [email],
        message: assessNote.trim() || undefined,
      });
      const failed = res.data.failed || [];
      const parts: string[] = [];
      if (assessMode === "from_job") {
        parts.push("Assessment created from this job’s JD.");
      }
      parts.push(`Sent ${res.data.sent} assessment invite email(s).`);
      if (failed.length) {
        parts.push(`Failed (${failed.length}): ${failed.join(", ")}`);
      }
      parts.push(`Invite link: ${absoluteLink(res.data.invite_link)}`);
      setAssessStatus(parts.join(" "));
      setAssessDeliveryNote(res.data.delivery_note || null);
      setCopyMsg(absoluteLink(res.data.invite_link));

      if (selectedJob) {
        const appsRes = await jobsLiveApi.listApplications(selectedJob);
        setApps(appsRes.data ?? []);
      }
    } catch (err) {
      onError(
        err instanceof Error ? err.message : "Could not send assessment invite",
      );
    } finally {
      setAssessBusy(false);
    }
  }

  const inviteRoom = liveRooms.find((r) => r.token === inviteRoomToken);
  const selectedJobTitle =
    jobs.find((j) => j.token === selectedJob)?.title || "this job";

  return (
    <section className="rp-card rp-card-wide rp-section">
      <div className="rp-field-row" style={{ alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <h2 className="rp-section-title">Jobs</h2>
          <label htmlFor="job-title">Job title</label>
          <input
            id="job-title"
            value={jobTitle}
            onChange={(e) => setJobTitle(e.target.value)}
            placeholder="Backend Engineer"
          />
          <div className="rp-tabs rp-tabs-spaced" style={{ marginBottom: "0.5rem" }}>
            <button
              type="button"
              className={jdMode === "paste" ? "active" : undefined}
              onClick={() => setJdMode("paste")}
              disabled={busy || parsingJd}
            >
              Paste JD
            </button>
            <button
              type="button"
              className={jdMode === "upload" ? "active" : undefined}
              onClick={() => setJdMode("upload")}
              disabled={busy || parsingJd}
            >
              Upload JD file
            </button>
          </div>
          {jdMode === "paste" ? (
            <div className="rp-jd-mode-block">
              <label htmlFor="job-jd">Job description</label>
              <textarea
                id="job-jd"
                rows={6}
                value={jobJd}
                onChange={(e) => setJobJd(e.target.value)}
                placeholder="Paste JD (skills, requirements…)"
                disabled={busy}
              />
            </div>
          ) : (
            <div className="rp-file-block rp-jd-mode-block">
              <label htmlFor="job-jd-file">JD file (PDF, Word, TXT)</label>
              <input
                id="job-jd-file"
                type="file"
                accept=".pdf,.doc,.docx,.txt,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                disabled={busy || parsingJd}
                onChange={(e) => setJdFile(e.target.files?.[0] ?? null)}
              />
              {jdFile && (
                <p className="rp-file-name">{jdFile.name}</p>
              )}
              {jobJd.trim().length >= 20 && (
                <p className="rp-muted-small rp-file-meta">
                  Extracted {jobJd.trim().length} characters.
                </p>
              )}
            </div>
          )}
          <button
            type="button"
            className="rp-primary rp-create-job-btn"
            disabled={busy || parsingJd}
            onClick={() => void createJob()}
          >
            {parsingJd
              ? "Reading JD file…"
              : busy
                ? "Creating…"
                : "Create job"}
          </button>
        </div>
        <div style={{ flex: 1 }}>
          <h2 className="rp-section-title">Live interviews</h2>
          <label htmlFor="meet-url">Meet / Zoom URL (optional)</label>
          <input
            id="meet-url"
            value={meetUrl}
            onChange={(e) => setMeetUrl(e.target.value)}
            placeholder="https://meet.google.com/..."
          />
          <label htmlFor="live-title">Room title</label>
          <input
            id="live-title"
            value={liveTitle}
            onChange={(e) => setLiveTitle(e.target.value)}
          />
          <button
            type="button"
            className="rp-secondary"
            disabled={busy}
            onClick={() => void startLive()}
          >
            Create live room
          </button>
        </div>
      </div>

      {copyMsg && (
        <p className="rp-copy-success">
          {copyMsg.startsWith("http") ? (
            <>
              Link:{" "}
              <a href={copyMsg} target="_blank" rel="noreferrer">
                {copyMsg}
              </a>{" "}
              <button
                type="button"
                className="rp-secondary rp-btn-compact"
                onClick={() => void navigator.clipboard.writeText(copyMsg)}
              >
                Copy
              </button>
            </>
          ) : (
            copyMsg
          )}
        </p>
      )}

      {assessApp && (
        <div className="rp-send-invites" style={{ marginTop: "1rem" }}>
          <h3 className="rp-preview-title" style={{ marginTop: 0 }}>
            Send assessment invite — {assessApp.full_name}
          </h3>

          <div className="rp-tabs rp-tabs-spaced" style={{ marginBottom: "0.75rem" }}>
            <button
              type="button"
              className={assessMode === "existing" ? "active" : undefined}
              disabled={assessBusy}
              onClick={() => setAssessMode("existing")}
            >
              Use existing assessment
            </button>
            <button
              type="button"
              className={assessMode === "from_job" ? "active" : undefined}
              disabled={assessBusy || !selectedJob}
              onClick={() => setAssessMode("from_job")}
            >
              Create from this job’s JD
            </button>
          </div>

          {assessMode === "existing" ? (
            assessments.length === 0 ? (
              <p className="rp-empty">No active assessments yet.</p>
            ) : (
              <label className="rp-muted-small" style={{ display: "block" }}>
                Assessment
                <select
                  value={assessToken}
                  onChange={(e) => setAssessToken(e.target.value)}
                  disabled={assessBusy}
                  style={{ display: "block", width: "100%", marginTop: "0.25rem" }}
                >
                  {assessments.map((a) => (
                    <option key={a.token} value={a.token}>
                      {(a.role_preview || "Assessment").slice(0, 60)} ·{" "}
                      {a.question_count}q · {a.difficulty}
                      {a.is_expired ? " (expired)" : ""}
                    </option>
                  ))}
                </select>
              </label>
            )
          ) : (
            <div className="rp-field-row" style={{ gap: "0.75rem" }}>
              <label className="rp-muted-small" style={{ flex: 1 }}>
                Difficulty
                <select
                  value={assessDifficulty}
                  onChange={(e) => setAssessDifficulty(e.target.value)}
                  disabled={assessBusy}
                  style={{ display: "block", width: "100%", marginTop: "0.25rem" }}
                >
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </label>
              <label className="rp-muted-small" style={{ flex: 1 }}>
                Questions
                <input
                  type="number"
                  min={3}
                  max={15}
                  value={assessQuestionCount}
                  onChange={(e) =>
                    setAssessQuestionCount(
                      Math.min(15, Math.max(3, Number(e.target.value) || 5)),
                    )
                  }
                  disabled={assessBusy}
                />
              </label>
              <label className="rp-muted-small" style={{ flex: 1 }}>
                Expiry (hours)
                <select
                  value={assessExpiryHours}
                  onChange={(e) => setAssessExpiryHours(Number(e.target.value))}
                  disabled={assessBusy}
                  style={{ display: "block", width: "100%", marginTop: "0.25rem" }}
                >
                  <option value={24}>24</option>
                  <option value={48}>48</option>
                  <option value={72}>72</option>
                  <option value={168}>168</option>
                </select>
              </label>
            </div>
          )}

          <label className="rp-muted-small" style={{ display: "block", marginTop: "0.75rem" }}>
            Candidate email
            <input
              type="email"
              value={assessEmail}
              onChange={(e) => setAssessEmail(e.target.value)}
              disabled={assessBusy}
              placeholder="candidate@gmail.com"
            />
          </label>
          <label className="rp-muted-small" style={{ display: "block", marginTop: "0.5rem" }}>
            Optional note
            <input
              type="text"
              value={assessNote}
              onChange={(e) => setAssessNote(e.target.value)}
              disabled={assessBusy}
              placeholder="Complete within 48 hours; laptop required"
            />
          </label>
          <div className="rp-actions" style={{ marginTop: "0.75rem" }}>
            <button
              type="button"
              className="rp-primary rp-btn-inline"
              disabled={
                assessBusy ||
                (assessMode === "existing" && !assessToken) ||
                (assessMode === "from_job" && !selectedJob)
              }
              onClick={() => void sendAssessmentInvite()}
            >
              {assessBusy
                ? assessMode === "from_job"
                  ? "Creating + sending…"
                  : "Sending…"
                : "Send assessment invite"}
            </button>
            <button
              type="button"
              className="rp-secondary rp-btn-compact"
              disabled={assessBusy}
              onClick={() => {
                setAssessApp(null);
                setAssessStatus(null);
                setAssessDeliveryNote(null);
              }}
            >
              Dismiss
            </button>
          </div>
          {assessStatus && <p className="rp-copy-success">{assessStatus}</p>}
          {assessDeliveryNote && (
            <p className="rp-copy-warning">{assessDeliveryNote}</p>
          )}
        </div>
      )}

      {inviteRoomToken && (
        <div className="rp-send-invites" style={{ marginTop: "1rem" }}>
          <h3 className="rp-preview-title" style={{ marginTop: 0 }}>
            Email live interview invite
            {inviteRoom ? ` — ${inviteRoom.title}` : ""}
          </h3>
          <label className="rp-muted-small">
            Candidate name (optional)
            <input
              type="text"
              value={inviteCandidateName}
              onChange={(e) => setInviteCandidateName(e.target.value)}
              placeholder="Alex Candidate"
              disabled={inviteSending}
            />
          </label>
          <label className="rp-muted-small" style={{ display: "block", marginTop: "0.5rem" }}>
            Emails (comma or new line)
            <textarea
              rows={2}
              value={inviteEmails}
              onChange={(e) => setInviteEmails(e.target.value)}
              placeholder="candidate@gmail.com"
              disabled={inviteSending}
            />
          </label>
          <label className="rp-muted-small" style={{ display: "block", marginTop: "0.5rem" }}>
            Optional note
            <input
              type="text"
              value={inviteMessage}
              onChange={(e) => setInviteMessage(e.target.value)}
              placeholder="Join 5 minutes early; laptop required"
              disabled={inviteSending}
            />
          </label>
          <div className="rp-actions" style={{ marginTop: "0.75rem" }}>
            <button
              type="button"
              className="rp-primary rp-btn-inline"
              disabled={inviteSending}
              onClick={() => void sendLiveInvite()}
            >
              {inviteSending ? "Sending…" : "Send invite email"}
            </button>
            <button
              type="button"
              className="rp-secondary rp-btn-compact"
              disabled={inviteSending}
              onClick={() => {
                setInviteRoomToken(null);
                setInviteStatus(null);
                setInviteDeliveryNote(null);
              }}
            >
              Dismiss
            </button>
          </div>
          {inviteStatus && <p className="rp-copy-success">{inviteStatus}</p>}
          {inviteDeliveryNote && (
            <p className="rp-copy-warning">{inviteDeliveryNote}</p>
          )}
        </div>
      )}

      <h3 className="rp-preview-title">Your jobs</h3>
      {jobs.length === 0 ? (
        <p className="rp-empty">No jobs yet.</p>
      ) : (
        <div className="recruiter-table-wrap">
          <table className="recruiter-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Applicants</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.token} className="rp-row-static">
                  <td>{j.title}</td>
                  <td>{j.application_count}</td>
                  <td>
                    <button
                      type="button"
                      className="rp-secondary rp-btn-compact"
                      onClick={() => setSelectedJob(j.token)}
                    >
                      View applicants
                    </button>{" "}
                    <button
                      type="button"
                      className="rp-secondary rp-btn-compact"
                      onClick={() => {
                        const url = absoluteLink(j.apply_link);
                        setCopyMsg(url);
                        void navigator.clipboard.writeText(url);
                      }}
                    >
                      Copy apply link
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedJob && (
        <>
          <h3 className="rp-preview-title">
            Applicants — {selectedJobTitle}
          </h3>
          {apps.length === 0 ? (
            <p className="rp-empty">No applicants yet.</p>
          ) : (
            <div className="recruiter-table-wrap">
              <table className="recruiter-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Score</th>
                    <th>Matched</th>
                    <th>Gaps</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {apps.map((a) => (
                    <tr key={a.id} className="rp-row-static">
                      <td>
                        {a.full_name}
                        <br />
                        <span className="rp-muted-small">{a.email}</span>
                      </td>
                      <td>
                        {a.ats_score}
                        {a.fit_label ? ` · ${a.fit_label}` : ""}
                      </td>
                      <td className="rp-muted-small">
                        {(a.matched_skills || []).slice(0, 6).join(", ") || "—"}
                      </td>
                      <td className="rp-muted-small">
                        {(a.missing_skills || []).slice(0, 6).join(", ") || "—"}
                      </td>
                      <td>{a.status}</td>
                      <td>
                        <button
                          type="button"
                          className="rp-secondary rp-btn-compact"
                          onClick={() => void setStatus(a.id, "shortlisted")}
                        >
                          Shortlist
                        </button>{" "}
                        <button
                          type="button"
                          className="rp-secondary rp-btn-compact"
                          onClick={() => void setStatus(a.id, "rejected")}
                        >
                          Reject
                        </button>{" "}
                        <button
                          type="button"
                          className="rp-primary rp-btn-compact"
                          onClick={() => openAssessmentInvite(a)}
                        >
                          Send assessment
                        </button>{" "}
                        <button
                          type="button"
                          className="rp-secondary rp-btn-compact"
                          onClick={() =>
                            void startLive({
                              applicationId: a.id,
                              candidateName: a.full_name,
                              candidateEmail: a.email,
                            })
                          }
                        >
                          Live interview
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <h3 className="rp-preview-title">Recent live rooms</h3>
      {liveRooms.length === 0 ? (
        <p className="rp-empty">No live rooms yet.</p>
      ) : (
        <ul className="rp-questions-editor">
          {liveRooms.slice(0, 8).map((r) => (
            <li key={r.token} className="rp-question-edit-row">
              {r.title} · {r.status}{" "}
              <a href={`${r.join_link}?role=recruiter`} target="_blank" rel="noreferrer">
                Open as recruiter
              </a>{" "}
              ·{" "}
              <a href={`${r.join_link}?role=candidate`} target="_blank" rel="noreferrer">
                Candidate link
              </a>{" "}
              ·{" "}
              <button
                type="button"
                className="rp-secondary rp-btn-compact"
                disabled={r.status === "ended"}
                onClick={() =>
                  openInviteForm({
                    token: r.token,
                    email: inviteRoomToken === r.token ? inviteEmails : "",
                    name: inviteRoomToken === r.token ? inviteCandidateName : "",
                  })
                }
              >
                Email invite
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
