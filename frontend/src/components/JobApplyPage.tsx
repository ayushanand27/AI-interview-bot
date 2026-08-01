import { useEffect, useState } from "react";
import { jobsLiveApi } from "../api/client";
import "../invite-flow.css";

export default function JobApplyPage({ token }: { token: string }) {
  const [title, setTitle] = useState("");
  const [jdPreview, setJdPreview] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [bootLoading, setBootLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobMissing, setJobMissing] = useState(false);
  const [result, setResult] = useState<{
    ats_score: number;
    fit_label?: string;
    matched_skills: string[];
    missing_skills: string[];
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setBootLoading(true);
    setJobMissing(false);
    jobsLiveApi
      .getPublicJob(token)
      .then((res) => {
        if (cancelled) return;
        setTitle(res.data.title);
        setJdPreview(res.data.jd_preview);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setJobMissing(true);
        setError(err instanceof Error ? err.message : "Job not found");
      })
      .finally(() => {
        if (!cancelled) setBootLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Please upload your resume (PDF/Word/TXT)");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await jobsLiveApi.applyToJob({
        token,
        full_name: name,
        email,
        resume: file,
      });
      setResult({
        ats_score: res.data.ats_score,
        fit_label: res.data.fit_label,
        matched_skills: res.data.matched_skills ?? [],
        missing_skills: res.data.missing_skills ?? [],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Apply failed");
    } finally {
      setLoading(false);
    }
  }

  if (bootLoading) {
    return (
      <div className="invite-flow">
        <div className="card loading">Loading job posting…</div>
      </div>
    );
  }

  if (jobMissing) {
    return (
      <div className="invite-flow">
        <div className="card status-panel">
          <h2 className="section-title">Job unavailable</h2>
          <p className="invite-meta">
            {error || "This apply link is invalid or the job was removed."}
          </p>
          <div className="actions" style={{ marginTop: "1.25rem" }}>
            <a href="/" className="primary" style={{ textDecoration: "none" }}>
              Back to home
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="invite-flow">
      <div className="card hero-card">
        <h1 className="section-title" style={{ marginBottom: "0.35rem" }}>
          {title || "Apply"}
        </h1>
        <p className="invite-meta" style={{ marginBottom: "1rem" }}>
          Upload your resume to apply.
        </p>
        {jdPreview && (
          <pre className="apply-jd-preview">{jdPreview}</pre>
        )}
        {error && <div className="alert error">{error}</div>}
        {result ? (
          <div className="apply-result">
            <div className="alert success">Application received</div>
            <p className="apply-score">
              ATS score: <strong>{result.ats_score}</strong>
              {result.fit_label ? (
                <span className="apply-fit"> · {result.fit_label}</span>
              ) : null}
            </p>
            {result.matched_skills.length > 0 && (
              <div className="apply-skills">
                <h3>Matched skills</h3>
                <p>{result.matched_skills.join(", ")}</p>
              </div>
            )}
            {result.missing_skills.length > 0 && (
              <div className="apply-skills apply-skills-gap">
                <h3>Gaps</h3>
                <p>{result.missing_skills.join(", ")}</p>
              </div>
            )}
            <p className="invite-meta" style={{ marginTop: "1rem" }}>
              We’ll be in touch if you’re shortlisted.
            </p>
          </div>
        ) : (
          <form className="invite-details-form" onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="apply-name">Full name</label>
              <input
                id="apply-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                disabled={loading}
                autoComplete="name"
              />
            </div>
            <div className="field">
              <label htmlFor="apply-email">Email</label>
              <input
                id="apply-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={loading}
                autoComplete="email"
              />
            </div>
            <div className="field">
              <label htmlFor="apply-resume">Resume (PDF, Word, or TXT)</label>
              <input
                id="apply-resume"
                type="file"
                accept=".pdf,.doc,.docx,.txt"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
                disabled={loading}
              />
              {file && (
                <p className="invite-meta" style={{ marginTop: "0.35rem" }}>
                  Selected: {file.name}
                </p>
              )}
            </div>
            <button type="submit" className="primary" disabled={loading}>
              {loading ? "Scoring…" : "Submit application"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
