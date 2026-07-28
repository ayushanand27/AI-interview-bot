import { useEffect, useState } from "react";
import { interviewApi, recruiterApi } from "../api/client";
import type {
  RecruiterSessionDetail,
  RecruiterSessionSummary,
} from "../types/recruiter";
import type {
  AssessmentQuestion,
  AssessmentSummary,
  QuestionType,
} from "../types/assessment";
import "../recruiter-portal.css";

const DEFAULT_TIME_SECONDS =
  Number(import.meta.env.VITE_QUESTION_TIMER_SECONDS) || 180;
const MIN_QUESTIONS = 2;
const MAX_QUESTIONS = 20;

const QUESTION_TYPE_OPTIONS: { value: QuestionType; label: string }[] = [
  { value: "subjective", label: "Subjective" },
  { value: "mcq", label: "MCQ (single)" },
  { value: "msq", label: "MSQ (multi)" },
  { value: "numerical", label: "Numerical" },
];

function emptyOptions(): string[] {
  return ["", "", "", ""];
}

function defaultQuestion(type: QuestionType = "subjective"): AssessmentQuestion {
  const base: AssessmentQuestion = {
    text: "",
    type,
    time_seconds: DEFAULT_TIME_SECONDS,
    marks: 10,
  };
  if (type === "mcq" || type === "msq") {
    base.options = emptyOptions();
    base.correct_indices = type === "mcq" ? [0] : [0, 1];
  }
  if (type === "numerical") {
    base.correct_answer = "";
    base.tolerance = 0;
  }
  return base;
}

function normalizeEditableQuestion(q: AssessmentQuestion): AssessmentQuestion {
  const type = (q.type || "subjective") as QuestionType;
  const next: AssessmentQuestion = {
    text: q.text ?? "",
    type,
    time_seconds: Number(q.time_seconds) || DEFAULT_TIME_SECONDS,
    marks: Number(q.marks) || 10,
  };
  if (type === "mcq" || type === "msq") {
    const options =
      q.options && q.options.length >= 2 ? [...q.options] : emptyOptions();
    while (options.length < 2) options.push("");
    next.options = options;
    next.correct_indices =
      q.correct_indices && q.correct_indices.length > 0
        ? [...q.correct_indices]
        : type === "mcq"
          ? [0]
          : [0];
  }
  if (type === "numerical") {
    next.correct_answer = q.correct_answer ?? "";
    next.tolerance = Number(q.tolerance ?? 0);
  }
  return next;
}

const VIOLATION_TYPE_LABELS: Record<string, string> = {
  no_face: "Face not detected",
  multiple_faces: "Multiple faces detected",
  looking_sideways: "Looking away (sideways)",
  looking_down: "Looking down",
  loud_audio: "Loud environment",
  tab_switch: "Switched away from interview window",
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
  const [questionTypes, setQuestionTypes] = useState<QuestionType[]>([
    "subjective",
    "mcq",
    "msq",
    "numerical",
  ]);
  const [assessmentLoading, setAssessmentLoading] = useState(false);
  const [editableQuestions, setEditableQuestions] = useState<AssessmentQuestion[]>(
    [],
  );
  const [draftJdText, setDraftJdText] = useState("");
  const [approvedInviteLink, setApprovedInviteLink] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  const [assessments, setAssessments] = useState<AssessmentSummary[]>([]);
  const [assessmentsLoading, setAssessmentsLoading] = useState(false);
  const [deletingToken, setDeletingToken] = useState<string | null>(null);
  const [extendingToken, setExtendingToken] = useState<string | null>(null);
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
      const res = await recruiterApi.generateQuestions({
        jd_text: jdMode === "paste" ? jdText.trim() : "",
        jd_pdf: jdMode === "pdf" ? jdPdfFile : null,
        question_count: questionCount,
        difficulty,
        question_types: questionTypes,
      });
      setEditableQuestions(
        (res.data.questions ?? []).map((q) => normalizeEditableQuestion(q)),
      );
      setDraftJdText(
        res.data.jd_text?.trim() ||
          (jdMode === "paste" ? jdText.trim() : ""),
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to generate questions");
    } finally {
      setAssessmentLoading(false);
    }
  }

  function updateQuestion(
    index: number,
    patch: Partial<AssessmentQuestion>,
  ) {
    setEditableQuestions((prev) =>
      prev.map((q, i) => (i === index ? { ...q, ...patch } : q)),
    );
  }

  function removeQuestion(index: number) {
    if (editableQuestions.length <= MIN_QUESTIONS) {
      onError(`Keep at least ${MIN_QUESTIONS} questions.`);
      return;
    }
    setEditableQuestions((prev) => prev.filter((_, i) => i !== index));
  }

  function toggleQuestionType(type: QuestionType) {
    setQuestionTypes((prev) => {
      if (prev.includes(type)) {
        if (prev.length === 1) return prev;
        return prev.filter((t) => t !== type);
      }
      return [...prev, type];
    });
  }

  function changeQuestionType(index: number, type: QuestionType) {
    setEditableQuestions((prev) =>
      prev.map((q, i) => {
        if (i !== index) return q;
        const next = defaultQuestion(type);
        next.text = q.text;
        next.time_seconds = q.time_seconds;
        next.marks = q.marks;
        if ((type === "mcq" || type === "msq") && q.options?.length) {
          next.options = [...q.options];
          next.correct_indices =
            type === "mcq"
              ? [q.correct_indices?.[0] ?? 0]
              : q.correct_indices?.length
                ? [...q.correct_indices]
                : [0];
        }
        if (type === "numerical") {
          next.correct_answer = q.correct_answer ?? "";
          next.tolerance = q.tolerance ?? 0;
        }
        return next;
      }),
    );
  }

  function updateOption(qi: number, oi: number, value: string) {
    setEditableQuestions((prev) =>
      prev.map((q, i) => {
        if (i !== qi) return q;
        const options = [...(q.options ?? emptyOptions())];
        options[oi] = value;
        return { ...q, options };
      }),
    );
  }

  function addOption(qi: number) {
    setEditableQuestions((prev) =>
      prev.map((q, i) => {
        if (i !== qi) return q;
        const options = [...(q.options ?? [])];
        if (options.length >= 8) return q;
        options.push("");
        return { ...q, options };
      }),
    );
  }

  function removeOption(qi: number, oi: number) {
    setEditableQuestions((prev) =>
      prev.map((q, i) => {
        if (i !== qi) return q;
        const options = [...(q.options ?? [])];
        if (options.length <= 2) return q;
        options.splice(oi, 1);
        const correct_indices = (q.correct_indices ?? [])
          .filter((idx) => idx !== oi)
          .map((idx) => (idx > oi ? idx - 1 : idx));
        return {
          ...q,
          options,
          correct_indices:
            correct_indices.length > 0
              ? correct_indices
              : q.type === "mcq"
                ? [0]
                : [0],
        };
      }),
    );
  }

  function toggleCorrectIndex(qi: number, oi: number) {
    setEditableQuestions((prev) =>
      prev.map((q, i) => {
        if (i !== qi) return q;
        if (q.type === "mcq") {
          return { ...q, correct_indices: [oi] };
        }
        const current = new Set(q.correct_indices ?? []);
        if (current.has(oi)) current.delete(oi);
        else current.add(oi);
        const correct_indices = Array.from(current).sort((a, b) => a - b);
        return {
          ...q,
          correct_indices: correct_indices.length ? correct_indices : [oi],
        };
      }),
    );
  }

  function addQuestion() {
    if (editableQuestions.length >= MAX_QUESTIONS) {
      onError(`At most ${MAX_QUESTIONS} questions are allowed.`);
      return;
    }
    setEditableQuestions((prev) => [...prev, defaultQuestion("subjective")]);
  }

  async function handleCreateAssessment() {
    const cleaned: AssessmentQuestion[] = [];
    for (const q of editableQuestions) {
      const text = q.text.trim();
      if (text.length < 3) continue;
      const type = (q.type || "subjective") as QuestionType;
      const base: AssessmentQuestion = {
        text,
        type,
        time_seconds: Number(q.time_seconds) || DEFAULT_TIME_SECONDS,
        marks: Number(q.marks) || 10,
      };
      if (type === "mcq" || type === "msq") {
        const options = (q.options ?? [])
          .map((o) => o.trim())
          .filter((o) => o.length > 0);
        if (options.length < 2) {
          onError(`Each ${type.toUpperCase()} needs at least 2 options.`);
          return;
        }
        const correct_indices = (q.correct_indices ?? []).filter(
          (idx) => idx >= 0 && idx < options.length,
        );
        if (type === "mcq" && correct_indices.length !== 1) {
          onError("Each MCQ needs exactly one correct option.");
          return;
        }
        if (type === "msq" && correct_indices.length < 1) {
          onError("Each MSQ needs at least one correct option.");
          return;
        }
        base.options = options;
        base.correct_indices =
          type === "mcq" ? [correct_indices[0]] : correct_indices;
      }
      if (type === "numerical") {
        const correct_answer = String(q.correct_answer ?? "").trim();
        if (!correct_answer || Number.isNaN(Number(correct_answer))) {
          onError("Numerical questions need a numeric correct answer.");
          return;
        }
        base.correct_answer = correct_answer;
        base.tolerance = Number(q.tolerance ?? 0);
      }
      cleaned.push(base);
    }

    if (cleaned.length < MIN_QUESTIONS) {
      onError(`Add at least ${MIN_QUESTIONS} questions with text.`);
      return;
    }

    setAssessmentLoading(true);
    onError(null);
    setCopyMessage(null);
    try {
      const res = await recruiterApi.createAssessment({
        jd_text: draftJdText || (jdMode === "paste" ? jdText.trim() : ""),
        jd_pdf:
          !draftJdText && jdMode === "pdf" ? jdPdfFile : null,
        question_count: cleaned.length,
        difficulty,
        expiry_hours: expiryHours,
        questions: cleaned,
      });
      setApprovedInviteLink(res.data.invite_link);
      setEditableQuestions(
        (res.data.questions_preview ?? cleaned).map((q) =>
          normalizeEditableQuestion(q),
        ),
      );
      loadAssessments();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to create assessment");
    } finally {
      setAssessmentLoading(false);
    }
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

  async function handleExtendAssessment(token: string, e: React.MouseEvent) {
    e.stopPropagation();
    const hoursRaw = window.prompt(
      "Extend expiry by how many hours from now?\nValid: 24, 48, 72, or 168",
      "48",
    );
    if (hoursRaw == null) return;
    const hours = Number(hoursRaw.trim());
    if (![24, 48, 72, 168].includes(hours)) {
      onError("Expiry must be 24, 48, 72, or 168 hours.");
      return;
    }
    setExtendingToken(token);
    onError(null);
    try {
      const res = await recruiterApi.updateAssessmentExpiry(token, hours);
      if (res.data) {
        setAssessments((prev) =>
          prev.map((a) => (a.token === token ? res.data : a)),
        );
        setCopyMessage("Invite expiry updated.");
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to extend expiry");
    } finally {
      setExtendingToken(null);
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

  const overallScore =
    detail?.final_score?.final_score ??
    detail?.final_score?.candidate_score ??
    detail?.adjusted_score ??
    detail?.original_score ??
    null;

  return (
    <div className="recruiter-portal">
      <header className="rp-header">
        <div className="rp-header-text">
          <h1>AI Interview Bot</h1>
          <p>Recruiter portal — assessments and interview review</p>
        </div>
        {onLogout && (
          <button
            type="button"
            className="rp-secondary rp-btn-compact"
            onClick={onLogout}
          >
            Log out
          </button>
        )}
      </header>

      <section className="rp-card rp-card-wide rp-section">
        <div className="rp-toolbar">
          <div>
            <h2 className="rp-section-title">Assessments</h2>
            <p className="rp-section-desc">Create invite links from a job description.</p>
          </div>
          <button
            type="button"
            className="rp-primary rp-btn-inline"
            onClick={() => {
              setShowAssessmentForm((v) => !v);
              setApprovedInviteLink(null);
              setCopyMessage(null);
              setEditableQuestions([]);
            }}
          >
            {showAssessmentForm ? "Cancel" : "New assessment"}
          </button>
        </div>

        {showAssessmentForm && (
          <div className="rp-form-panel">
            <div className="rp-tabs rp-tabs-spaced">
              <button
                type="button"
                className={jdMode === "paste" ? "active" : undefined}
                onClick={() => {
                  setJdMode("paste");
                  onError(null);
                }}
              >
                Paste text
              </button>
              <button
                type="button"
                className={jdMode === "pdf" ? "active" : undefined}
                onClick={() => {
                  setJdMode("pdf");
                  onError(null);
                }}
              >
                Upload file
              </button>
            </div>

            <div className="rp-jd-url-block">
              <label htmlFor="jd-url">Job posting URL (optional)</label>
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
                  className="rp-secondary rp-btn-compact"
                  onClick={() => void handleFetchJd()}
                  disabled={fetchingJd || assessmentLoading || !jdUrl.trim()}
                >
                  {fetchingJd ? "…" : "Fetch"}
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
                  <p className="rp-file-name">{jdPdfFile.name}</p>
                )}
              </div>
            )}

            <div className="rp-field-row">
              <div>
                <label htmlFor="question-count">Questions</label>
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
                <label htmlFor="expiry">Expires</label>
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

            <div className="rp-type-mix">
              <span className="rp-type-mix-label">Question types to generate</span>
              <div className="rp-type-mix-options">
                {QUESTION_TYPE_OPTIONS.map((opt) => (
                  <label key={opt.value} className="rp-type-chip">
                    <input
                      type="checkbox"
                      checked={questionTypes.includes(opt.value)}
                      onChange={() => toggleQuestionType(opt.value)}
                      disabled={assessmentLoading}
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>

            <button
              type="button"
              className="rp-primary"
              disabled={assessmentLoading}
              onClick={() => void handleGenerateQuestions()}
            >
              {assessmentLoading && editableQuestions.length === 0
                ? "Generating…"
                : "Generate questions"}
            </button>

            {editableQuestions.length > 0 && (
              <div className="rp-preview-block">
                <div className="rp-preview-header">
                  <h3 className="rp-preview-title">Edit questions</h3>
                  <p className="rp-muted-small">
                    Adjust type, wording, options, correct answers, time, and marks.
                  </p>
                </div>
                <ol className="rp-questions-editor">
                  {editableQuestions.map((q, i) => (
                    <li key={i} className="rp-question-edit-row">
                      <div className="rp-question-edit-top">
                        <span className="rp-question-num">Q{i + 1}</span>
                        <label className="rp-inline-type">
                          Type
                          <select
                            value={q.type || "subjective"}
                            onChange={(e) =>
                              changeQuestionType(
                                i,
                                e.target.value as QuestionType,
                              )
                            }
                            disabled={assessmentLoading}
                          >
                            {QUESTION_TYPE_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          type="button"
                          className="rp-secondary rp-btn-compact"
                          disabled={
                            assessmentLoading ||
                            editableQuestions.length <= MIN_QUESTIONS
                          }
                          onClick={() => removeQuestion(i)}
                        >
                          Remove
                        </button>
                      </div>
                      <textarea
                        value={q.text}
                        onChange={(e) =>
                          updateQuestion(i, { text: e.target.value })
                        }
                        rows={3}
                        disabled={assessmentLoading}
                        placeholder="Question text"
                      />
                      {(q.type === "mcq" || q.type === "msq") && (
                        <div className="rp-options-editor">
                          <p className="rp-muted-small">
                            Options — mark correct
                            {q.type === "msq" ? " (multi)" : " (one)"}
                          </p>
                          {(q.options ?? []).map((opt, oi) => (
                            <div key={oi} className="rp-option-row">
                              <input
                                type={q.type === "mcq" ? "radio" : "checkbox"}
                                name={`correct-${i}`}
                                checked={(q.correct_indices ?? []).includes(oi)}
                                onChange={() => toggleCorrectIndex(i, oi)}
                                disabled={assessmentLoading}
                                title="Mark as correct"
                              />
                              <input
                                type="text"
                                value={opt}
                                onChange={(e) =>
                                  updateOption(i, oi, e.target.value)
                                }
                                placeholder={`Option ${oi + 1}`}
                                disabled={assessmentLoading}
                              />
                              <button
                                type="button"
                                className="rp-secondary rp-btn-compact"
                                disabled={
                                  assessmentLoading ||
                                  (q.options?.length ?? 0) <= 2
                                }
                                onClick={() => removeOption(i, oi)}
                              >
                                ×
                              </button>
                            </div>
                          ))}
                          <button
                            type="button"
                            className="rp-secondary rp-btn-compact"
                            disabled={
                              assessmentLoading || (q.options?.length ?? 0) >= 8
                            }
                            onClick={() => addOption(i)}
                          >
                            Add option
                          </button>
                        </div>
                      )}
                      {q.type === "numerical" && (
                        <div className="rp-question-meta-row">
                          <label>
                            Correct answer
                            <input
                              type="text"
                              value={q.correct_answer ?? ""}
                              onChange={(e) =>
                                updateQuestion(i, {
                                  correct_answer: e.target.value,
                                })
                              }
                              disabled={assessmentLoading}
                              placeholder="e.g. 42"
                            />
                          </label>
                          <label>
                            Tolerance ±
                            <input
                              type="number"
                              min={0}
                              step={0.01}
                              value={q.tolerance ?? 0}
                              onChange={(e) =>
                                updateQuestion(i, {
                                  tolerance: Number(e.target.value) || 0,
                                })
                              }
                              disabled={assessmentLoading}
                            />
                          </label>
                        </div>
                      )}
                      <div className="rp-question-meta-row">
                        <label>
                          Time (sec)
                          <input
                            type="number"
                            min={30}
                            max={3600}
                            step={30}
                            value={q.time_seconds}
                            onChange={(e) =>
                              updateQuestion(i, {
                                time_seconds:
                                  Number(e.target.value) || DEFAULT_TIME_SECONDS,
                              })
                            }
                            disabled={assessmentLoading}
                          />
                        </label>
                        <label>
                          Marks
                          <input
                            type="number"
                            min={0.5}
                            max={100}
                            step={0.5}
                            value={q.marks}
                            onChange={(e) =>
                              updateQuestion(i, {
                                marks: Number(e.target.value) || 10,
                              })
                            }
                            disabled={assessmentLoading}
                          />
                        </label>
                      </div>
                    </li>
                  ))}
                </ol>
                <div className="rp-actions">
                  <button
                    type="button"
                    className="rp-secondary"
                    disabled={
                      assessmentLoading ||
                      editableQuestions.length >= MAX_QUESTIONS
                    }
                    onClick={addQuestion}
                  >
                    Add question
                  </button>
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
                    disabled={assessmentLoading}
                    onClick={() => void handleCreateAssessment()}
                  >
                    {assessmentLoading ? "Creating…" : "Create & get link"}
                  </button>
                </div>
              </div>
            )}

            {approvedInviteLink && (
              <div className="rp-invite-box">
                <p className="rp-invite-hint">Candidate invite link</p>
                <p className="rp-invite-link">{fullInviteUrl(approvedInviteLink)}</p>
                <div className="rp-actions">
                  <button
                    type="button"
                    className="rp-secondary"
                    onClick={() => void handleCopyLink()}
                  >
                    Copy link
                  </button>
                </div>
                {copyMessage && (
                  <p className="rp-copy-success">{copyMessage}</p>
                )}
              </div>
            )}
          </div>
        )}

        {assessments.length > 0 && (
          <div className={showAssessmentForm ? "rp-list-block" : undefined}>
            {showAssessmentForm && (
              <h3 className="rp-preview-title">Saved invites</h3>
            )}
            {assessmentsLoading ? (
              <p className="rp-muted-small">Loading…</p>
            ) : (
              <div className="recruiter-table-wrap">
                <table className="recruiter-table">
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th>Qs</th>
                      <th>Uses</th>
                      <th>Expires</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assessments.map((a) => (
                      <tr key={a.token} className="rp-row-static">
                        <td>
                          {a.role_preview}
                          {a.is_expired && (
                            <span className="rp-expired"> · expired</span>
                          )}
                        </td>
                        <td>
                          {a.question_count}
                          <span className="rp-cell-muted"> {a.difficulty}</span>
                        </td>
                        <td>
                          {a.used_count}/{a.max_uses}
                        </td>
                        <td>{formatDate(a.expiry_at)}</td>
                        <td>
                          <div className="rp-row-actions">
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
                            <button
                              type="button"
                              className="rp-secondary rp-btn-compact"
                              disabled={extendingToken === a.token}
                              onClick={(e) =>
                                void handleExtendAssessment(a.token, e)
                              }
                            >
                              {extendingToken === a.token ? "…" : "Extend"}
                            </button>
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
                              onClick={(e) =>
                                void handleDeleteAssessment(a.token, e)
                              }
                            >
                              {deletingToken === a.token ? "…" : "Delete"}
                            </button>
                          </div>
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
      </section>

      <section className="rp-card rp-card-wide rp-section">
        <h2 className="rp-section-title">Completed interviews</h2>
        <p className="rp-section-desc">
          Select a row to open the transcript and proctoring summary.
        </p>

        {loading && sessions.length === 0 ? (
          <p className="rp-muted-small rp-loading-inline">Loading interviews…</p>
        ) : sessions.length === 0 ? (
          <p className="rp-empty">
            No completed interviews yet. Candidates must finish a session before
            it appears here.
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
                  <th>Status</th>
                  <th>Actions</th>
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
                      <div className="rp-row-actions">
                        {row.recording_available && (
                          <button
                            type="button"
                            className="rp-secondary rp-btn-compact"
                            disabled={watchingId === row.session_id}
                            onClick={(e) => handleWatchRecording(row, e)}
                          >
                            {watchingId === row.session_id ? "…" : "Watch"}
                          </button>
                        )}
                        <button
                          type="button"
                          className="rp-secondary rp-btn-compact"
                          disabled={downloadingId === row.session_id}
                          onClick={(e) => handleDownloadReport(row, e)}
                        >
                          {downloadingId === row.session_id ? "…" : "PDF"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedId && (
        <section className="rp-card rp-card-wide rp-section">
          {detailLoading || !detail ? (
            <p className="rp-muted-small rp-loading-inline">Loading transcript…</p>
          ) : (
            <>
              <div className="rp-detail-header">
                <div>
                  <h2 className="rp-section-title">
                    {detail.candidate_name}
                  </h2>
                  <p className="rp-detail-meta">
                    {detail.role_title}
                    {" · "}
                    {formatDate(detail.date)}
                    {detail.duration_minutes != null
                      ? ` · ${detail.duration_minutes} min`
                      : ""}
                    {" · "}
                    {detail.answered_count}/{detail.total_questions} answered
                    {" · "}
                    {detail.status}
                  </p>
                </div>
                <div className="rp-detail-actions">
                  <button
                    type="button"
                    className="rp-secondary rp-btn-compact"
                    disabled={reviewUpdating}
                    onClick={() =>
                      void handleToggleHumanReview(!detail.human_review_flag)
                    }
                  >
                    {reviewUpdating
                      ? "…"
                      : detail.human_review_flag
                        ? "Clear flag"
                        : "Flag review"}
                  </button>
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
                    {downloadingId === detail.session_id ? "…" : "Download PDF"}
                  </button>
                  {detail.recording_available && (
                    <button
                      type="button"
                      className="rp-secondary rp-btn-compact"
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
                      {watchingId === detail.session_id ? "…" : "Watch"}
                    </button>
                  )}
                </div>
              </div>

              {detail.human_review_flag && (
                <div className="alert warning rp-summary-spaced">
                  Flagged for human review.
                </div>
              )}

              {detail.low_identity_confidence && (
                <div className="alert warning rp-summary-spaced">
                  Identity verification needs review
                  {detail.identity_similarity_score != null && (
                    <>
                      {" "}
                      (face match: {detail.identity_similarity_score.toFixed(2)})
                    </>
                  )}
                  .
                </div>
              )}

              {(overallScore != null ||
                detail.integrity_penalty_percent > 0 ||
                detail.final_score?.recommendation) && (
                <div className="rp-score-panel">
                  <div className="rp-score-main">
                    <span className="rp-score-label">Score</span>
                    <span className="rp-score-value">
                      {overallScore ?? "—"}
                      <span className="rp-score-max"> / 100</span>
                    </span>
                  </div>
                  <div className="rp-score-meta">
                    {detail.original_score != null &&
                      detail.adjusted_score != null &&
                      detail.original_score !== detail.adjusted_score && (
                        <span>
                          Original {detail.original_score}
                          {detail.integrity_penalty_percent > 0 && (
                            <> · −{detail.integrity_penalty_percent}% integrity</>
                          )}
                        </span>
                      )}
                    {detail.integrity_level && (
                      <span>Integrity: {detail.integrity_level}</span>
                    )}
                    {detail.final_score?.recommendation && (
                      <span>
                        Rec: <strong>{detail.final_score.recommendation}</strong>
                      </span>
                    )}
                  </div>
                </div>
              )}

              {detail.proctoring_summary?.violations &&
                detail.proctoring_summary.violations.length > 0 && (
                  <section className="rp-violations-panel">
                    <h3 className="rp-preview-title">Proctoring</h3>
                    <ul className="summary-violations-list">
                      {detail.proctoring_summary.violations.map((v, idx) => (
                        <li key={`${v.time}-${idx}`}>
                          {new Date(v.time * 1000).toLocaleTimeString()} ·{" "}
                          {formatViolationType(v.type)} ({v.severity}) · −
                          {v.penalty_percent}%
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

              <div className="rp-transcript">
                {detail.transcript.map((item) => {
                  const j = item.judgment;
                  return (
                    <div key={item.index} className="summary-item">
                      <h3>Q{item.index}</h3>
                      <p>{item.question}</p>
                      <h3 className="rp-answer-title">Answer</h3>
                      <p className="answer-text">
                        {item.answer ?? "(not answered)"}
                      </p>
                      {j && !j.error && (
                        <div className="summary-feedback">
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
              </div>
            </>
          )}
        </section>
      )}
      <p className="rp-footer">
        <a href="/privacy">Privacy Policy</a>
      </p>
    </div>
  );
}
