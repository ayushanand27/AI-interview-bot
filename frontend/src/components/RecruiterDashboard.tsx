import { useEffect, useState } from "react";
import { interviewApi, recruiterApi } from "../api/client";
import type {
  RecruiterSessionDetail,
  RecruiterSessionSummary,
} from "../types/recruiter";
import type { AssessmentSummary } from "../types/assessment";
import "../recruiter-portal.css";

const VIOLATION_TYPE_LABELS: Record<string, string> = {
  no_face: "Face not detected",
  multiple_faces: "Multiple faces detected",
  looking_sideways: "Looking away (sideways)",
  looking_down: "Looking down",
  loud_audio: "Loud environment",
  tab_switch: "Tab switch",
  virtual_camera: "Virtual camera",
  virtual_camera_suspected: "Unusual camera setup",
  recording_extension: "Screen recording extension",
  screen_sharing: "Screen sharing",
  prohibited_object_detected: "Prohibited object detected (cell phone)",
};

function formatViolationType(type: string): string {
  return VIOLATION_TYPE_LABELS[type] ?? type.replace(/_/g, " ");
}

const DOCUMENT_ACCEPT =
  ".pdf,.doc,.docx,.txt,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";

const JD_FETCH_ERROR =
  "Could not extract JD from this URL — please paste manually";

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatScore(score: number | null): string {
  if (score === null || Number.isNaN(score)) return "—";
  return String(Math.round(score));
}

function fullInviteUrl(relativeLink: string): string {
  return `${window.location.origin}${relativeLink}`;
}

interface RecruiterDashboardProps {
  loading: boolean;
  onLoadingChange: (loading: boolean) => void;
  onError: (message: string | null) => void;
  onLogout?: () => void;
}

export default function RecruiterDashboard({
  loading,
  onLoadingChange,
  onError,
  onLogout,
}: RecruiterDashboardProps) {
  const [sessions, setSessions] = useState<RecruiterSessionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RecruiterSessionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [watchingId, setWatchingId] = useState<string | null>(null);

  const [showAssessmentForm, setShowAssessmentForm] = useState(false);
  const [jdMode, setJdMode] = useState<"paste" | "pdf">("paste");
  const [jdText, setJdText] = useState("");
  const [jdUrl, setJdUrl] = useState("");
  const [fetchingJd, setFetchingJd] = useState(false);
  const [jdPdfFile, setJdPdfFile] = useState<File | null>(null);
  const [questionCount, setQuestionCount] = useState(5);
  const [difficulty, setDifficulty] = useState("Medium");
  const [expiryHours, setExpiryHours] = useState(48);
  const [assessmentLoading, setAssessmentLoading] = useState(false);
  const [questionsPreview, setQuestionsPreview] = useState<string[]>([]);
  const [pendingInviteLink, setPendingInviteLink] = useState<string | null>(null);
  const [approvedInviteLink, setApprovedInviteLink] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  const [assessments, setAssessments] = useState<AssessmentSummary[]>([]);
  const [assessmentsLoading, setAssessmentsLoading] = useState(false);
  const [deletingToken, setDeletingToken] = useState<string | null>(null);
  const [reviewUpdating, setReviewUpdating] = useState(false);

  function loadAssessments() {
    setAssessmentsLoading(true);
    recruiterApi
      .listAssessments()
      .then((res) => setAssessments(res.data ?? []))
      .catch(() => {
        /* non-blocking — list is optional on dashboard */
      })
      .finally(() => setAssessmentsLoading(false));
  }

  useEffect(() => {
    loadAssessments();
  }, []);

  useEffect(() => {
    let cancelled = false;
    onLoadingChange(true);
    onError(null);

    recruiterApi
      .listSessions()
      .then((res) => {
        if (!cancelled) {
          setSessions(res.data ?? []);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          onError(err instanceof Error ? err.message : "Failed to load sessions");
        }
      })
      .finally(() => {
        if (!cancelled) {
          onLoadingChange(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [onError, onLoadingChange]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }

    let cancelled = false;
    setDetailLoading(true);
    onError(null);

    recruiterApi
      .getSession(selectedId)
      .then((res) => {
        if (!cancelled) {
          setDetail(res.data);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          onError(err instanceof Error ? err.message : "Failed to load session");
          setDetail(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setDetailLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId, onError]);

  async function handleWatchRecording(
    row: RecruiterSessionSummary,
    e: React.MouseEvent,
  ) {
    e.stopPropagation();
    setWatchingId(row.session_id);
    onError(null);
    try {
      const blob = await recruiterApi.getRecording(row.session_id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load recording");
    } finally {
      setWatchingId(null);
    }
  }

  async function handleDownloadReport(
    row: RecruiterSessionSummary,
    e: React.MouseEvent,
  ) {
    e.stopPropagation();
    setDownloadingId(row.session_id);
    onError(null);
    try {
      const blob = await recruiterApi.downloadReport(row.session_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `interview-report-${row.candidate_name.replace(/\s+/g, "-")}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to download report");
    } finally {
      setDownloadingId(null);
    }
  }

  async function handleFetchJd() {
    const url = jdUrl.trim();
    if (!url) {
      onError("Enter a job posting URL first.");
      return;
    }
    setFetchingJd(true);
    onError(null);
    try {
      const result = await interviewApi.fetchJdUrl(url);
      setJdText(result.jd_text);
      setJdMode("paste");
    } catch (err) {
      const message = err instanceof Error ? err.message : JD_FETCH_ERROR;
      onError(
        message.toLowerCase().includes("extract") ? message : JD_FETCH_ERROR,
      );
    } finally {
      setFetchingJd(false);
    }
  }

  async function handleGenerateQuestions() {
    if (jdMode === "paste" && !jdText.trim()) {
      onError("Please paste a job description or switch to Upload JD file.");
      return;
    }
    if (jdMode === "pdf" && !jdPdfFile) {
      onError(
        "Please upload a job description file (PDF, Word, or TXT) or switch to Paste JD Text.",
      );
      return;
    }
    setAssessmentLoading(true);
    onError(null);
    setApprovedInviteLink(null);
    setCopyMessage(null);
    try {
      const res = await recruiterApi.createAssessment({
        jd_text: jdMode === "paste" ? jdText.trim() : "",
        jd_pdf: jdMode === "pdf" ? jdPdfFile : null,
        question_count: questionCount,
        difficulty,
        expiry_hours: expiryHours,
      });
      setQuestionsPreview(res.data.questions_preview);
      setPendingInviteLink(res.data.invite_link);
      loadAssessments();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to generate questions");
    } finally {
      setAssessmentLoading(false);
    }
  }

  function handleApprove() {
    if (!pendingInviteLink) return;
    setApprovedInviteLink(pendingInviteLink);
    setCopyMessage(null);
  }

  async function handleCopyLink() {
    if (!approvedInviteLink) return;
    const url = fullInviteUrl(approvedInviteLink);
    try {
      await navigator.clipboard.writeText(url);
      setCopyMessage("Link copied to clipboard.");
    } catch {
      setCopyMessage("Could not copy — select and copy the link manually.");
    }
  }

  async function handleDeleteAssessment(token: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (!window.confirm("Delete this unused assessment invite?")) return;
    setDeletingToken(token);
    onError(null);
    try {
      await recruiterApi.deleteAssessment(token);
      setAssessments((prev) => prev.filter((a) => a.token !== token));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to delete assessment");
    } finally {
      setDeletingToken(null);
    }
  }

  async function handleToggleHumanReview(flagged: boolean) {
    if (!detail) return;
    setReviewUpdating(true);
    onError(null);
    try {
      const res = await recruiterApi.setHumanReview(detail.session_id, flagged);
      const updated = res.data;
      if (updated) {
        setDetail(updated);
        setSessions((prev) =>
          prev.map((s) =>
            s.session_id === updated.session_id
              ? { ...s, human_review_flag: updated.human_review_flag }
              : s,
          ),
        );
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to update review flag");
    } finally {
      setReviewUpdating(false);
    }
  }

  return (
    <div className="recruiter-portal">
      <header>
        <h1>AI Interview Bot — Recruiter Portal</h1>
        <p>Create assessments and review completed interviews.</p>
        {onLogout && (
          <button
            type="button"
            className="rp-secondary rp-logout"
            onClick={onLogout}
          >
            Log out
          </button>
        )}
      </header>

      <div className="rp-card rp-card-wide rp-card-spacing">
        <div className="rp-toolbar">
          <h2 className="rp-section-title">Assessments</h2>
          <button
            type="button"
            className="rp-primary rp-btn-inline"
            onClick={() => {
              setShowAssessmentForm((v) => !v);
              setApprovedInviteLink(null);
              setCopyMessage(null);
            }}
          >
            {showAssessmentForm ? "Hide form" : "Create New Assessment"}
          </button>
        </div>

        {showAssessmentForm && (
          <>
            <label>Job description</label>
            <div className="rp-tabs rp-tabs-spaced">
              <button
                type="button"
                className={jdMode === "paste" ? "active" : undefined}
                onClick={() => {
                  setJdMode("paste");
                  onError(null);
                }}
              >
                Paste JD Text
              </button>
              <button
                type="button"
                className={jdMode === "pdf" ? "active" : undefined}
                onClick={() => {
                  setJdMode("pdf");
                  onError(null);
                }}
              >
                Upload JD File
              </button>
            </div>

            <div className="rp-jd-url-block">
              <label htmlFor="jd-url" className="rp-jd-url-label">
                Or paste a job URL
              </label>
              <div className="rp-jd-url-row">
                <input
                  id="jd-url"
                  type="url"
                  value={jdUrl}
                  onChange={(e) => setJdUrl(e.target.value)}
                  placeholder="https://www.indeed.com/viewjob?..."
                  disabled={fetchingJd || assessmentLoading}
                />
                <button
                  type="button"
                  className="rp-secondary"
                  onClick={() => void handleFetchJd()}
                  disabled={fetchingJd || assessmentLoading || !jdUrl.trim()}
                >
                  {fetchingJd ? "Fetching…" : "Fetch JD"}
                </button>
              </div>
            </div>

            {jdMode === "paste" ? (
              <textarea
                id="jd-text"
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="Paste the full job description…"
              />
            ) : (
              <div className="rp-file-block">
                <input
                  id="jd-pdf"
                  type="file"
                  accept={DOCUMENT_ACCEPT}
                  onChange={(e) => {
                    setJdPdfFile(e.target.files?.[0] ?? null);
                  }}
                />
                {jdPdfFile && (
                  <p className="rp-file-name">Selected: {jdPdfFile.name}</p>
                )}
              </div>
            )}

            <div className="rp-field-row">
              <div>
                <label htmlFor="question-count">Number of questions</label>
                <select
                  id="question-count"
                  value={questionCount}
                  onChange={(e) => setQuestionCount(Number(e.target.value))}
                >
                  <option value={2}>2</option>
                  <option value={5}>5</option>
                  <option value={10}>10</option>
                  <option value={15}>15</option>
                  <option value={20}>20</option>
                </select>
              </div>
              <div>
                <label htmlFor="difficulty">Difficulty</label>
                <select
                  id="difficulty"
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value)}
                >
                  <option value="Easy">Easy</option>
                  <option value="Medium">Medium</option>
                  <option value="Hard">Hard</option>
                </select>
              </div>
              <div>
                <label htmlFor="expiry">Link expiry</label>
                <select
                  id="expiry"
                  value={expiryHours}
                  onChange={(e) => setExpiryHours(Number(e.target.value))}
                >
                  <option value={24}>24 hours</option>
                  <option value={48}>48 hours</option>
                  <option value={72}>72 hours</option>
                  <option value={168}>1 week</option>
                </select>
              </div>
            </div>

            <button
              type="button"
              className="rp-primary"
              disabled={assessmentLoading}
              onClick={() => void handleGenerateQuestions()}
            >
              {assessmentLoading ? "Generating…" : "Generate Questions"}
            </button>

            {questionsPreview.length > 0 && (
              <div className="rp-preview-block">
                <h3 className="rp-preview-title">Question preview</h3>
                <ol className="rp-questions-preview">
                  {questionsPreview.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ol>
                <div className="rp-actions">
                  <button
                    type="button"
                    className="rp-secondary"
                    disabled={assessmentLoading}
                    onClick={() => void handleGenerateQuestions()}
                  >
                    Regenerate
                  </button>
                  <button
                    type="button"
                    className="rp-primary rp-btn-inline"
                    disabled={!pendingInviteLink}
                    onClick={handleApprove}
                  >
                    Approve &amp; Get Link
                  </button>
                </div>
              </div>
            )}

            {approvedInviteLink && (
              <div className="rp-invite-box">
                <p className="rp-invite-hint">
                  Share this invite link with candidates:
                </p>
                <p className="rp-invite-link">{fullInviteUrl(approvedInviteLink)}</p>
                <div className="rp-actions">
                  <button type="button" className="rp-secondary" onClick={() => void handleCopyLink()}>
                    Copy to clipboard
                  </button>
                </div>
                {copyMessage && (
                  <p className="rp-copy-success">{copyMessage}</p>
                )}
              </div>
            )}
          </>
        )}

        {assessments.length > 0 && (
          <div className="rp-preview-block">
            <h3 className="rp-preview-title">Saved assessments</h3>
            {assessmentsLoading ? (
              <p className="rp-muted-small">Loading…</p>
            ) : (
              <div className="recruiter-table-wrap">
                <table className="recruiter-table">
                  <thead>
                    <tr>
                      <th>Role preview</th>
                      <th>Questions</th>
                      <th>Uses</th>
                      <th>Expires</th>
                      <th>Link</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {assessments.map((a) => (
                      <tr key={a.token}>
                        <td>
                          {a.role_preview}
                          {a.is_expired && (
                            <span className="rp-expired"> · expired</span>
                          )}
                        </td>
                        <td>
                          {a.question_count} ({a.difficulty})
                        </td>
                        <td>
                          {a.used_count}/{a.max_uses}
                        </td>
                        <td>{formatDate(a.expiry_at)}</td>
                        <td>
                          <button
                            type="button"
                            className="rp-secondary rp-btn-compact"
                            onClick={() => {
                              void navigator.clipboard.writeText(
                                fullInviteUrl(a.invite_link),
                              );
                              setCopyMessage("Invite link copied.");
                            }}
                          >
                            Copy
                          </button>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="rp-secondary rp-btn-compact"
                            disabled={
                              deletingToken === a.token || a.used_count > 0
                            }
                            title={
                              a.used_count > 0
                                ? "Cannot delete after a candidate has started"
                                : "Delete unused invite"
                            }
                            onClick={(e) => void handleDeleteAssessment(a.token, e)}
                          >
                            {deletingToken === a.token ? "…" : "Delete"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {copyMessage && !approvedInviteLink && (
              <p className="rp-copy-success">{copyMessage}</p>
            )}
          </div>
        )}
      </div>

      <div className="rp-card rp-card-wide recruiter-dashboard">
        <h2 className="rp-section-title-spaced">Completed interviews</h2>

        {loading && sessions.length === 0 ? (
          <p className="loading">Loading interviews…</p>
        ) : sessions.length === 0 ? (
          <p className="rp-empty">
            No completed interviews yet. Candidates must finish and end a session
            before it appears here.
          </p>
        ) : (
          <div className="recruiter-table-wrap">
            <table className="recruiter-table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Role</th>
                  <th>Date</th>
                  <th>Score</th>
                  <th>Review</th>
                  <th>Recording</th>
                  <th>Report</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((row) => (
                  <tr
                    key={row.session_id}
                    className={
                      selectedId === row.session_id ? "selected" : undefined
                    }
                    onClick={() => setSelectedId(row.session_id)}
                  >
                    <td>{row.candidate_name}</td>
                    <td>{row.role_title}</td>
                    <td>{formatDate(row.date)}</td>
                    <td>
                      {formatScore(row.final_score)}
                      {row.recommendation ? (
                        <span className="recruiter-rec">
                          {" "}
                          · {row.recommendation}
                        </span>
                      ) : null}
                    </td>
                    <td>
                      {row.human_review_flag ? (
                        <span className="rp-review-badge">Review</span>
                      ) : (
                        <span className="rp-muted-small">—</span>
                      )}
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {row.recording_available ? (
                        <button
                          type="button"
                          className="rp-secondary rp-btn-compact"
                          disabled={watchingId === row.session_id}
                          onClick={(e) => handleWatchRecording(row, e)}
                        >
                          {watchingId === row.session_id
                            ? "Loading…"
                            : "Watch Recording"}
                        </button>
                      ) : (
                        <span className="rp-muted-small">No</span>
                      )}
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="rp-secondary rp-btn-compact"
                        disabled={downloadingId === row.session_id}
                        onClick={(e) => handleDownloadReport(row, e)}
                      >
                        {downloadingId === row.session_id
                          ? "Downloading…"
                          : "Download Report"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedId && (
        <div className="rp-card rp-card-wide rp-card-spacing-top">
          {detailLoading || !detail ? (
            <p className="loading">Loading transcript…</p>
          ) : (
            <>
              <div className="rp-detail-header">
                <h2 className="rp-section-title-tight">
                  {detail.candidate_name} — {detail.role_title}
                </h2>
                <div className="rp-detail-actions">
                  {detail.human_review_flag ? (
                    <button
                      type="button"
                      className="rp-secondary"
                      disabled={reviewUpdating}
                      onClick={() => void handleToggleHumanReview(false)}
                    >
                      {reviewUpdating ? "Updating…" : "Clear review flag"}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="rp-secondary"
                      disabled={reviewUpdating}
                      onClick={() => void handleToggleHumanReview(true)}
                    >
                      {reviewUpdating ? "Updating…" : "Flag for review"}
                    </button>
                  )}
                  <button
                    type="button"
                    className="rp-primary rp-btn-inline"
                    disabled={downloadingId === detail.session_id}
                    onClick={(e) => {
                      const row = sessions.find(
                        (s) => s.session_id === detail.session_id,
                      );
                      if (row) {
                        void handleDownloadReport(row, e);
                      }
                    }}
                  >
                    {downloadingId === detail.session_id
                      ? "Downloading…"
                      : "Download Report"}
                  </button>
                  {detail.recording_available && (
                    <button
                      type="button"
                      className="rp-secondary"
                      disabled={watchingId === detail.session_id}
                      onClick={(e) => {
                        const row = sessions.find(
                          (s) => s.session_id === detail.session_id,
                        );
                        if (row) {
                          void handleWatchRecording(row, e);
                        }
                      }}
                    >
                      {watchingId === detail.session_id
                        ? "Loading…"
                        : "Watch Recording"}
                    </button>
                  )}
                </div>
              </div>
              <p className="rp-detail-meta">
                {formatDate(detail.date)}
                {detail.duration_minutes != null
                  ? ` · ${detail.duration_minutes} min`
                  : ""}{" "}
                · {detail.answered_count} of {detail.total_questions} answered ·{" "}
                {detail.status}
                {detail.recording_available ? " · Recording available" : ""}
              </p>

              {detail.human_review_flag && (
                <div className="alert warning rp-summary-spaced">
                  This session is flagged for human review.
                </div>
              )}

              {detail.low_identity_confidence && (
                <div className="alert warning rp-summary-spaced">
                  Identity verification flagged for review
                  {detail.identity_similarity_score != null && (
                    <>
                      {" "}
                      (face match score:{" "}
                      {detail.identity_similarity_score.toFixed(2)})
                    </>
                  )}
                  . ID photo and selfie similarity was below the confidence threshold.
                </div>
              )}

              {(detail.original_score != null || detail.adjusted_score != null) && (
                <div className="summary-overall rp-summary-spaced">
                  <h3>Scores</h3>
                  {detail.original_score != null && (
                    <p>Original score: <strong>{detail.original_score}</strong> / 100</p>
                  )}
                  {detail.integrity_penalty_percent > 0 && (
                    <p>Integrity penalty: <strong>-{detail.integrity_penalty_percent}%</strong></p>
                  )}
                  {detail.adjusted_score != null && (
                    <p>Adjusted score: <strong>{detail.adjusted_score}</strong> / 100</p>
                  )}
                  {detail.integrity_level && (
                    <p>Integrity level: <strong>{detail.integrity_level}</strong></p>
                  )}
                </div>
              )}

              {detail.proctoring_summary?.violations &&
                detail.proctoring_summary.violations.length > 0 && (
                  <section className="summary-violations rp-summary-spaced">
                    <h3>Proctoring violations</h3>
                    <ul className="summary-violations-list">
                      {detail.proctoring_summary.violations.map((v, idx) => (
                        <li key={`${v.time}-${idx}`}>
                          {new Date(v.time * 1000).toLocaleTimeString()} ·{" "}
                          {formatViolationType(v.type)} ({v.severity}) · -
                          {v.penalty_percent}%
                          {v.message ? ` — ${v.message}` : ""}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

              {detail.final_score && (
                <div className="summary-overall rp-summary-spaced">
                  <h3>Overall score</h3>
                  <p className="summary-score">
                    <strong>
                      {detail.final_score.final_score ??
                        detail.final_score.candidate_score ??
                        "—"}
                    </strong>
                    <span className="summary-score-max"> / 100</span>
                  </p>
                  {detail.final_score.recommendation && (
                    <p className="summary-recommendation">
                      Recommendation:{" "}
                      <strong>{detail.final_score.recommendation}</strong>
                    </p>
                  )}
                </div>
              )}

              {detail.transcript.map((item) => {
                const j = item.judgment;
                return (
                  <div key={item.index} className="summary-item">
                    <h3>Question {item.index}</h3>
                    <p>{item.question}</p>
                    <h3 className="rp-answer-title">Answer</h3>
                    <p className="answer-text">
                      {item.answer ?? "(not answered)"}
                    </p>
                    {j && !j.error && (
                      <div className="summary-feedback">
                        <h3>Judge feedback</h3>
                        {j.weighted_total != null && (
                          <p className="summary-question-score">
                            Score: <strong>{j.weighted_total}</strong> / 100
                          </p>
                        )}
                        {(j.overall_reasoning ?? j.reasoning) && (
                          <p className="summary-reasoning">
                            {j.overall_reasoning ?? j.reasoning}
                          </p>
                        )}
                        {j.strengths && j.strengths.length > 0 && (
                          <div className="summary-feedback-block">
                            <h4>Strengths</h4>
                            <ul>
                              {j.strengths.map((s, idx) => (
                                <li key={idx}>{s}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {j.improvements && j.improvements.length > 0 && (
                          <div className="summary-feedback-block">
                            <h4>Improvements</h4>
                            <ul>
                              {j.improvements.map((s, idx) => (
                                <li key={idx}>{s}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                    {j?.error === "judging_failed" && (
                      <div className="alert info alert-stack">
                        Judge feedback unavailable for this answer.
                      </div>
                    )}
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}
      <p className="rp-footer">
        <a href="/privacy">Privacy Policy</a>
      </p>
    </div>
  );
}
