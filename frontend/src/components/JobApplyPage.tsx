import { useEffect, useState } from "react";
import { jobsLiveApi } from "../api/client";
import "../invite-flow.css";

export default function JobApplyPage({ token }: { token: string }) {
  const [title, setTitle] = useState("");
  const [jdPreview, setJdPreview] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    ats_score: number;
    fit_label?: string;
    matched_skills: string[];
    missing_skills: string[];
  } | null>(null);

  useEffect(() => {
    jobsLiveApi
      .getPublicJob(token)
      .then((res) => {
        setTitle(res.data.title);
        setJdPreview(res.data.jd_preview);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Job not found"),
      );
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

  return (
    <div className="invite-flow">
      <div className="invite-card">
        <h1>{title || "Apply"}</h1>
        {jdPreview && (
          <pre className="invite-jd-preview" style={{ whiteSpace: "pre-wrap" }}>
            {jdPreview}
          </pre>
        )}
        {error && <p className="invite-error">{error}</p>}
        {result ? (
          <div className="invite-success">
            <h2>Application received</h2>
            <p>
              ATS score: <strong>{result.ats_score}</strong>
              {result.fit_label ? ` · ${result.fit_label}` : ""}
            </p>
            {result.matched_skills.length > 0 && (
              <p>Matched: {result.matched_skills.join(", ")}</p>
            )}
            {result.missing_skills.length > 0 && (
              <p>Gaps: {result.missing_skills.join(", ")}</p>
            )}
            <p>The recruiter can shortlist you from the dashboard.</p>
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
              />
            </div>
            <div className="field">
              <label htmlFor="apply-resume">Resume</label>
              <input
                id="apply-resume"
                type="file"
                accept=".pdf,.doc,.docx,.txt"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
            </div>
            <button type="submit" className="invite-primary" disabled={loading}>
              {loading ? "Scoring…" : "Submit application"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
