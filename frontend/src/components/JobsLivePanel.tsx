import { useEffect, useState } from "react";
import { jobsLiveApi, recruiterApi } from "../api/client";

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

  useEffect(() => {
    refreshJobs();
    refreshLive();
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

  const inviteRoom = liveRooms.find((r) => r.token === inviteRoomToken);

  return (
    <section className="rp-card rp-card-wide rp-section">
      <h2 className="rp-section-title">Jobs · ATS shortlist · Live interview</h2>
      <p className="rp-section-desc">
        Create a job apply link, score resumes, shortlist, then open a shared
        live coding room and email the candidate their join link (video via
        Meet/Zoom URL).
      </p>

      <div className="rp-field-row" style={{ alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
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
            <>
              <label htmlFor="job-jd">Job description</label>
              <textarea
                id="job-jd"
                rows={6}
                value={jobJd}
                onChange={(e) => setJobJd(e.target.value)}
                placeholder="Paste JD (skills, requirements…)"
                disabled={busy}
              />
            </>
          ) : (
            <>
              <label htmlFor="job-jd-file">JD file (PDF, Word, TXT)</label>
              <input
                id="job-jd-file"
                type="file"
                accept=".pdf,.doc,.docx,.txt,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                disabled={busy || parsingJd}
                onChange={(e) => setJdFile(e.target.files?.[0] ?? null)}
              />
              {jdFile && (
                <p className="rp-file-name rp-muted-small">{jdFile.name}</p>
              )}
              {jobJd.trim().length >= 20 && (
                <p className="rp-muted-small">
                  Extracted {jobJd.trim().length} characters — ready to create.
                </p>
              )}
            </>
          )}
          <button
            type="button"
            className="rp-primary"
            disabled={busy || parsingJd}
            onClick={() => void createJob()}
          >
            {parsingJd
              ? "Reading JD file…"
              : busy
                ? "Creating…"
                : "Create job + apply link"}
          </button>
        </div>
        <div style={{ flex: 1 }}>
          <label htmlFor="meet-url">Default Meet / Zoom URL (optional)</label>
          <input
            id="meet-url"
            value={meetUrl}
            onChange={(e) => setMeetUrl(e.target.value)}
            placeholder="https://meet.google.com/..."
          />
          <label htmlFor="live-title">Live room title</label>
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

      {inviteRoomToken && (
        <div className="rp-send-invites" style={{ marginTop: "1rem" }}>
          <h3 className="rp-preview-title" style={{ marginTop: 0 }}>
            Email live interview invite
            {inviteRoom ? ` — ${inviteRoom.title}` : ""}
          </h3>
          <p className="rp-muted-small">
            Sends the candidate live room link
            {inviteRoom?.meet_url ? " and the Meet/Zoom URL stored on the room" : ""}
            .
          </p>
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
        <p className="rp-empty">No jobs yet — create one above to get an apply link.</p>
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
                      View
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
          <h3 className="rp-preview-title">Applicants (ATS ranked)</h3>
          {apps.length === 0 ? (
            <p className="rp-empty">
              No applicants yet. Share the apply link, then shortlist strong resumes here.
            </p>
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
                          onClick={() =>
                            void startLive({
                              applicationId: a.id,
                              candidateName: a.full_name,
                              candidateEmail: a.email,
                            })
                          }
                        >
                          Live interview
                        </button>{" "}
                        <button
                          type="button"
                          className="rp-secondary rp-btn-compact"
                          title="Copy email to paste into assessment invite"
                          onClick={() => {
                            void navigator.clipboard.writeText(a.email);
                            setCopyMsg(
                              `Email copied (${a.email}). Paste into Assessments → Send invite.`,
                            );
                          }}
                        >
                          Copy email for assessment
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
        <p className="rp-empty">
          No live rooms yet — create one or start from a shortlisted applicant.
        </p>
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
