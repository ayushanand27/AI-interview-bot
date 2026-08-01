import { useEffect, useState } from "react";
import { jobsLiveApi } from "../api/client";

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

export default function JobsLivePanel({
  onError,
  absoluteLink,
}: JobsLivePanelProps) {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [apps, setApps] = useState<AppRow[]>([]);
  const [jobTitle, setJobTitle] = useState("");
  const [jobJd, setJobJd] = useState("");
  const [meetUrl, setMeetUrl] = useState("");
  const [liveTitle, setLiveTitle] = useState("Live technical interview");
  const [liveRooms, setLiveRooms] = useState<LiveRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [copyMsg, setCopyMsg] = useState<string | null>(null);

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

  async function createJob() {
    setBusy(true);
    onError(null);
    try {
      const res = await jobsLiveApi.createJob({
        title: jobTitle,
        jd_text: jobJd,
      });
      setJobTitle("");
      setJobJd("");
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

  async function startLive(applicationId?: number, candidateName?: string) {
    setBusy(true);
    onError(null);
    try {
      const res = await jobsLiveApi.createLiveRoom({
        title: candidateName
          ? `Live with ${candidateName}`
          : liveTitle || "Live technical interview",
        meet_url: meetUrl || undefined,
        application_id: applicationId,
      });
      refreshLive();
      const link = absoluteLink(res.data.join_link);
      setCopyMsg(link);
      window.open(`${res.data.join_link}?role=recruiter`, "_blank");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Live room failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rp-card rp-card-wide rp-section">
      <h2 className="rp-section-title">Jobs · ATS shortlist · Live interview</h2>
      <p className="rp-section-desc">
        Create a job apply link, score resumes, shortlist, then open a shared
        live coding room (video via Meet/Zoom URL).
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
          <label htmlFor="job-jd">Job description</label>
          <textarea
            id="job-jd"
            rows={6}
            value={jobJd}
            onChange={(e) => setJobJd(e.target.value)}
            placeholder="Paste JD (skills, requirements…)"
          />
          <button
            type="button"
            className="rp-primary"
            disabled={busy}
            onClick={() => void createJob()}
          >
            Create job + apply link
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
        <p className="rp-copy-ok">
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
        </p>
      )}

      <h3 className="rp-preview-title">Your jobs</h3>
      <table className="rp-table">
        <thead>
          <tr>
            <th>Title</th>
            <th>Applicants</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.token}>
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

      {selectedJob && (
        <>
          <h3 className="rp-preview-title">Applicants (ATS ranked)</h3>
          <table className="rp-table">
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
                <tr key={a.id}>
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
                    {(a.matched_skills || []).slice(0, 6).join(", ")}
                  </td>
                  <td className="rp-muted-small">
                    {(a.missing_skills || []).slice(0, 6).join(", ")}
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
                      onClick={() => void startLive(a.id, a.full_name)}
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
                          `Email copied (${a.email}). Use Assessments → send invite.`,
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
        </>
      )}

      <h3 className="rp-preview-title">Recent live rooms</h3>
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
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
