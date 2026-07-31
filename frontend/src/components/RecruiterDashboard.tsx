import { useEffect, useState } from "react";
import { interviewApi, recruiterApi } from "../api/client";
import type {
  RecruiterAnalyticsResponse,
  RecruiterSessionDetail,
  RecruiterSessionFilters,
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
  { value: "coding", label: "Coding" },
];

const CODING_LANGUAGE_OPTIONS: { value: string; label: string }[] = [
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript" },
  { value: "java", label: "Java" },
  { value: "cpp", label: "C++" },
  { value: "c", label: "C" },
  { value: "perl", label: "Perl (view-only — not runnable)" },
];

const DEFAULT_STARTERS: Record<string, string> = {
  python:
    "# Read from stdin, write to stdout\ndef solve():\n    pass\n\nif __name__ == '__main__':\n    solve()\n",
  javascript:
    "const fs = require('fs');\nconst input = fs.readFileSync(0, 'utf8').trim();\nconsole.log(input);\n",
  java:
    "import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n    }\n}\n",
  cpp:
    "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    return 0;\n}\n",
  c: "#include <stdio.h>\n\nint main(void) {\n    return 0;\n}\n",
  perl: "#!/usr/bin/perl\nuse strict;\nuse warnings;\n\n",
};

function emptyTestCase() {
  return { stdin: "", expected_stdout: "" };
}

function emptyOptions(): string[] {
  return ["", "", "", ""];
}

function defaultQuestion(type: QuestionType = "subjective"): AssessmentQuestion {
  const base: AssessmentQuestion = {
    text: "",
    type,
    time_seconds: type === "coding" ? 900 : DEFAULT_TIME_SECONDS,
    marks: type === "coding" ? 20 : 10,
  };
  if (type === "mcq" || type === "msq") {
    base.options = emptyOptions();
    base.correct_indices = type === "mcq" ? [0] : [0, 1];
  }
  if (type === "numerical") {
    base.correct_answer = "";
    base.tolerance = 0;
  }
  if (type === "coding") {
    base.languages = ["python", "javascript"];
    base.starter_code = {
      python: DEFAULT_STARTERS.python,
      javascript: DEFAULT_STARTERS.javascript,
    };
    base.public_tests = [emptyTestCase()];
    base.hidden_tests = [emptyTestCase(), emptyTestCase()];
    base.time_limit_ms = 2000;
    base.memory_limit_mb = 128;
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
  if (type === "coding") {
    const languages =
      q.languages && q.languages.length > 0
        ? [...q.languages]
        : ["python", "javascript"];
    next.languages = languages;
    const starter: Record<string, string> = { ...(q.starter_code || {}) };
    for (const lang of languages) {
      if (!starter[lang]) starter[lang] = DEFAULT_STARTERS[lang] || "";
    }
    next.starter_code = starter;
    next.public_tests =
      q.public_tests && q.public_tests.length > 0
        ? q.public_tests.map((t) => ({
            stdin: t.stdin ?? "",
            expected_stdout: t.expected_stdout ?? "",
          }))
        : [emptyTestCase()];
    next.hidden_tests =
      q.hidden_tests && q.hidden_tests.length > 0
        ? q.hidden_tests.map((t) => ({
            stdin: t.stdin ?? "",
            expected_stdout: t.expected_stdout ?? "",
          }))
        : [emptyTestCase()];
    next.time_limit_ms = q.time_limit_ms ?? 2000;
    next.memory_limit_mb = q.memory_limit_mb ?? 128;
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

function formatReviewStatus(status: string | null | undefined): string {
  const normalized = (status ?? "pending").replace(/_/g, " ").trim();
  if (!normalized) return "Pending";
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase());
}

function reviewBadgeClass(status: string | null | undefined): string {
  switch (status) {
    case "cleared":
      return "rp-review-badge rp-review-badge-clear";
    case "rejected":
      return "rp-review-badge rp-review-badge-reject";
    case "escalated":
      return "rp-review-badge rp-review-badge-escalate";
    case "in_review":
      return "rp-review-badge rp-review-badge-progress";
    default:
      return "rp-review-badge";
  }
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}%`;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

const SCORE_BAND_OPTIONS = ["Strong Hire", "Hire", "Maybe", "No Hire", "Unscored"];
const INTEGRITY_OPTIONS = [
  "clean",
  "minor_concerns",
  "moderate_concerns",
  "serious_concerns",
  "unknown",
];
const REVIEW_STATUS_OPTIONS = [
  "pending",
  "needs_review",
  "in_review",
  "cleared",
  "escalated",
  "rejected",
];

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
  const [approvedInviteToken, setApprovedInviteToken] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [inviteEmailsText, setInviteEmailsText] = useState("");
  const [inviteNote, setInviteNote] = useState("");
  const [inviteSending, setInviteSending] = useState(false);
  const [inviteSendMessage, setInviteSendMessage] = useState<string | null>(null);

  const [assessments, setAssessments] = useState<AssessmentSummary[]>([]);
  const [assessmentsLoading, setAssessmentsLoading] = useState(false);
  const [deletingToken, setDeletingToken] = useState<string | null>(null);
  const [extendingToken, setExtendingToken] = useState<string | null>(null);
  const [reviewUpdating, setReviewUpdating] = useState(false);
  const [reviewNotesDraft, setReviewNotesDraft] = useState("");
  const [analytics, setAnalytics] = useState<RecruiterAnalyticsResponse | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [exportingSessions, setExportingSessions] = useState(false);
  const [exportingAssessments, setExportingAssessments] = useState(false);
  const [filters, setFilters] = useState<RecruiterSessionFilters>({});
  const [filterRole, setFilterRole] = useState("");
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");
  const [filterInviteToken, setFilterInviteToken] = useState("");
  const [filterScoreBand, setFilterScoreBand] = useState("");
  const [filterIntegrity, setFilterIntegrity] = useState("");
  const [filterReviewStatus, setFilterReviewStatus] = useState("");

  function buildFilters(): RecruiterSessionFilters {
    const next: RecruiterSessionFilters = {};
    if (filterRole.trim()) next.role_title = filterRole.trim();
    if (filterDateFrom) next.date_from = new Date(filterDateFrom).toISOString();
    if (filterDateTo) {
      const end = new Date(filterDateTo);
      end.setHours(23, 59, 59, 999);
      next.date_to = end.toISOString();
    }
    if (filterInviteToken.trim()) next.invite_token = filterInviteToken.trim();
    if (filterScoreBand) next.score_band = filterScoreBand;
    if (filterIntegrity) next.integrity_level = filterIntegrity;
    if (filterReviewStatus) next.review_status = filterReviewStatus;
    return next;
  }

  function loadSessions(activeFilters?: RecruiterSessionFilters) {
    const query = activeFilters ?? filters;
    onLoadingChange(true);
    onError(null);
    recruiterApi
      .listSessions(query)
      .then((res) => setSessions(res.data ?? []))
      .catch((err) => {
        onError(err instanceof Error ? err.message : "Failed to load sessions");
      })
      .finally(() => onLoadingChange(false));
  }

  function loadAnalytics(activeFilters?: RecruiterSessionFilters) {
    const query = activeFilters ?? filters;
    setAnalyticsLoading(true);
    recruiterApi
      .getAnalytics(query)
      .then((res) => setAnalytics(res.data ?? null))
      .catch(() => {
        /* analytics is supplementary */
      })
      .finally(() => setAnalyticsLoading(false));
  }

  function refreshDashboard(activeFilters?: RecruiterSessionFilters) {
    const query = activeFilters ?? filters;
    loadSessions(query);
    loadAnalytics(query);
  }

  function applyFilters() {
    const next = buildFilters();
    setFilters(next);
    refreshDashboard(next);
  }

  function clearFilters() {
    setFilterRole("");
    setFilterDateFrom("");
    setFilterDateTo("");
    setFilterInviteToken("");
    setFilterScoreBand("");
    setFilterIntegrity("");
    setFilterReviewStatus("");
    setFilters({});
    refreshDashboard({});
  }

  async function handleExportSessions() {
    setExportingSessions(true);
    onError(null);
    try {
      const blob = await recruiterApi.exportSessionsCsv(filters);
      downloadBlob(blob, `recruiter-sessions-${Date.now()}.csv`);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to export sessions");
    } finally {
      setExportingSessions(false);
    }
  }

  async function handleExportAssessments() {
    setExportingAssessments(true);
    onError(null);
    try {
      const blob = await recruiterApi.exportAssessmentsCsv();
      downloadBlob(blob, `recruiter-assessments-${Date.now()}.csv`);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to export assessments");
    } finally {
      setExportingAssessments(false);
    }
  }

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
    refreshDashboard({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setReviewNotesDraft("");
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
          setReviewNotesDraft(res.data?.review_state?.review_notes ?? "");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          onError(err instanceof Error ? err.message : "Failed to load session");
          setDetail(null);
          setReviewNotesDraft("");
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
        next.time_seconds =
          type === "coding"
            ? Math.max(q.time_seconds || 0, 600)
            : q.time_seconds;
        next.marks = type === "coding" ? Math.max(q.marks || 0, 20) : q.marks;
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
        if (type === "coding" && q.type === "coding") {
          next.languages = q.languages?.length
            ? [...q.languages]
            : next.languages;
          next.starter_code = q.starter_code
            ? { ...q.starter_code }
            : next.starter_code;
          next.public_tests = q.public_tests?.length
            ? q.public_tests.map((t) => ({ ...t }))
            : next.public_tests;
          next.hidden_tests = q.hidden_tests?.length
            ? q.hidden_tests.map((t) => ({ ...t }))
            : next.hidden_tests;
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
      if (type === "coding") {
        const languages = (q.languages ?? []).filter(Boolean);
        if (languages.length < 1) {
          onError("Coding questions need at least one language.");
          return;
        }
        const starter_code: Record<string, string> = {};
        for (const lang of languages) {
          starter_code[lang] =
            q.starter_code?.[lang] || DEFAULT_STARTERS[lang] || "";
        }
        const public_tests = (q.public_tests ?? [])
          .map((t) => ({
            stdin: t.stdin ?? "",
            expected_stdout: t.expected_stdout ?? "",
          }))
          .filter((t) => t.stdin.length > 0 || t.expected_stdout.length > 0);
        const hidden_tests = (q.hidden_tests ?? [])
          .map((t) => ({
            stdin: t.stdin ?? "",
            expected_stdout: t.expected_stdout ?? "",
          }))
          .filter((t) => t.stdin.length > 0 || t.expected_stdout.length > 0);
        if (public_tests.length + hidden_tests.length < 1) {
          onError("Coding questions need at least one public or hidden test.");
          return;
        }
        base.languages = languages;
        base.starter_code = starter_code;
        base.public_tests = public_tests;
        base.hidden_tests = hidden_tests;
        base.time_limit_ms = Number(q.time_limit_ms) || 2000;
        base.memory_limit_mb = Number(q.memory_limit_mb) || 128;
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
      setApprovedInviteToken(res.data.token);
      setInviteEmailsText("");
      setInviteNote("");
      setInviteSendMessage(null);
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

  async function handleSendInviteEmails() {
    if (!approvedInviteToken) return;
    const emails = inviteEmailsText
      .split(/[,;\n]+/)
      .map((e) => e.trim())
      .filter(Boolean);
    if (emails.length === 0) {
      onError("Add at least one email address to send invites.");
      return;
    }
    setInviteSending(true);
    setInviteSendMessage(null);
    onError(null);
    try {
      const res = await recruiterApi.sendAssessmentInvites(
        approvedInviteToken,
        {
          emails,
          message: inviteNote.trim() || undefined,
        },
      );
      const failed = res.data.failed?.length ?? 0;
      setInviteSendMessage(
        failed > 0
          ? `Sent ${res.data.sent}. Failed: ${res.data.failed.join(", ")}`
          : `Sent ${res.data.sent} invite email(s).`,
      );
    } catch (err) {
      onError(
        err instanceof Error ? err.message : "Failed to send invite emails",
      );
    } finally {
      setInviteSending(false);
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
        setReviewNotesDraft(updated.review_state?.review_notes ?? "");
        setSessions((prev) =>
          prev.map((s) =>
            s.session_id === updated.session_id
              ? {
                  ...s,
                  human_review_flag: updated.human_review_flag,
                  review_status: updated.review_state.review_status,
                  review_notes: updated.review_state.review_notes,
                  reviewed_at: updated.review_state.reviewed_at,
                  integrity_level: updated.integrity_level,
                  integrity_event_count: updated.integrity_event_count,
                  low_identity_confidence: updated.low_identity_confidence ?? false,
                }
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

  async function handleUpdateReviewState(reviewStatus: string) {
    if (!detail) return;
    setReviewUpdating(true);
    onError(null);
    try {
      const res = await recruiterApi.updateReviewState(detail.session_id, {
        review_status: reviewStatus,
        review_notes: reviewNotesDraft.trim() || null,
      });
      const updated = res.data;
      if (updated) {
        setDetail(updated);
        setReviewNotesDraft(updated.review_state.review_notes ?? "");
        setSessions((prev) =>
          prev.map((s) =>
            s.session_id === updated.session_id
              ? {
                  ...s,
                  human_review_flag: updated.human_review_flag,
                  review_status: updated.review_state.review_status,
                  review_notes: updated.review_state.review_notes,
                  reviewed_at: updated.review_state.reviewed_at,
                  integrity_level: updated.integrity_level,
                  integrity_event_count: updated.integrity_event_count,
                  low_identity_confidence: updated.low_identity_confidence ?? false,
                }
              : s,
          ),
        );
      }
    } catch (err) {
      onError(
        err instanceof Error ? err.message : "Failed to update review disposition",
      );
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
          <p>Assessments · reviews · analytics</p>
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
            <p className="rp-section-desc">JD → questions → invite link</p>
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
                placeholder="Paste job description…"
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
              <span className="rp-type-mix-label">Question types</span>
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
                  <h3 className="rp-preview-title">Questions</h3>
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
                                className="rp-option-text"
                                value={opt}
                                onChange={(e) =>
                                  updateOption(i, oi, e.target.value)
                                }
                                placeholder={`Option ${oi + 1}`}
                                disabled={assessmentLoading}
                                aria-label={`Option ${oi + 1}`}
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
                      {q.type === "coding" && (
                        <div className="rp-coding-editor">
                          <p className="rp-muted-small">
                            Languages (candidate can pick one)
                          </p>
                          <div className="rp-type-toggles">
                            {CODING_LANGUAGE_OPTIONS.map((opt) => {
                              const checked = (q.languages ?? []).includes(
                                opt.value,
                              );
                              return (
                                <label key={opt.value} className="rp-check">
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    disabled={assessmentLoading}
                                    onChange={() => {
                                      const current = new Set(
                                        q.languages ?? [],
                                      );
                                      if (current.has(opt.value)) {
                                        if (current.size <= 1) return;
                                        current.delete(opt.value);
                                      } else {
                                        current.add(opt.value);
                                      }
                                      const languages = Array.from(current);
                                      const starter = {
                                        ...(q.starter_code || {}),
                                      };
                                      for (const lang of languages) {
                                        if (!starter[lang]) {
                                          starter[lang] =
                                            DEFAULT_STARTERS[lang] || "";
                                        }
                                      }
                                      updateQuestion(i, {
                                        languages,
                                        starter_code: starter,
                                      });
                                    }}
                                  />
                                  {opt.label}
                                </label>
                              );
                            })}
                          </div>
                          {(q.languages ?? ["python"]).map((lang) => (
                            <label key={lang} className="rp-coding-starter">
                              Starter ({lang})
                              <textarea
                                rows={5}
                                value={q.starter_code?.[lang] ?? ""}
                                disabled={assessmentLoading}
                                onChange={(e) =>
                                  updateQuestion(i, {
                                    starter_code: {
                                      ...(q.starter_code || {}),
                                      [lang]: e.target.value,
                                    },
                                  })
                                }
                                placeholder={`Starter code for ${lang}`}
                              />
                            </label>
                          ))}
                          {(
                            [
                              ["public_tests", "Public tests"],
                              ["hidden_tests", "Hidden tests"],
                            ] as const
                          ).map(([field, label]) => (
                            <div key={field} className="rp-tests-editor">
                              <p className="rp-muted-small">{label}</p>
                              {(q[field] ?? [emptyTestCase()]).map((t, ti) => (
                                <div key={ti} className="rp-test-row">
                                  <textarea
                                    rows={2}
                                    placeholder="stdin"
                                    value={t.stdin}
                                    disabled={assessmentLoading}
                                    onChange={(e) => {
                                      const list = [
                                        ...(q[field] ?? [emptyTestCase()]),
                                      ];
                                      list[ti] = {
                                        ...list[ti],
                                        stdin: e.target.value,
                                      };
                                      updateQuestion(i, { [field]: list });
                                    }}
                                  />
                                  <textarea
                                    rows={2}
                                    placeholder="expected stdout"
                                    value={t.expected_stdout}
                                    disabled={assessmentLoading}
                                    onChange={(e) => {
                                      const list = [
                                        ...(q[field] ?? [emptyTestCase()]),
                                      ];
                                      list[ti] = {
                                        ...list[ti],
                                        expected_stdout: e.target.value,
                                      };
                                      updateQuestion(i, { [field]: list });
                                    }}
                                  />
                                  <button
                                    type="button"
                                    className="rp-secondary rp-btn-compact"
                                    disabled={
                                      assessmentLoading ||
                                      (q[field]?.length ?? 0) <= 1
                                    }
                                    onClick={() => {
                                      const list = [...(q[field] ?? [])];
                                      list.splice(ti, 1);
                                      updateQuestion(i, {
                                        [field]:
                                          list.length > 0
                                            ? list
                                            : [emptyTestCase()],
                                      });
                                    }}
                                  >
                                    ×
                                  </button>
                                </div>
                              ))}
                              <button
                                type="button"
                                className="rp-secondary rp-btn-compact"
                                disabled={assessmentLoading}
                                onClick={() =>
                                  updateQuestion(i, {
                                    [field]: [
                                      ...(q[field] ?? []),
                                      emptyTestCase(),
                                    ],
                                  })
                                }
                              >
                                Add {label.toLowerCase().replace(/s$/, "")}
                              </button>
                            </div>
                          ))}
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
                <div className="rp-send-invites" style={{ marginTop: "1rem" }}>
                  <p className="rp-invite-hint">
                    Email invite to candidates / institutions (industry-standard)
                  </p>
                  <label className="rp-muted-small">
                    Emails (comma or new line)
                    <textarea
                      rows={3}
                      value={inviteEmailsText}
                      onChange={(e) => setInviteEmailsText(e.target.value)}
                      placeholder="candidate@college.edu, hr@company.com"
                      disabled={inviteSending}
                    />
                  </label>
                  <label className="rp-muted-small" style={{ display: "block", marginTop: "0.5rem" }}>
                    Optional note
                    <input
                      type="text"
                      value={inviteNote}
                      onChange={(e) => setInviteNote(e.target.value)}
                      placeholder="Complete within 48 hours"
                      disabled={inviteSending}
                    />
                  </label>
                  <div className="rp-actions" style={{ marginTop: "0.75rem" }}>
                    <button
                      type="button"
                      className="rp-primary"
                      disabled={inviteSending || !approvedInviteToken}
                      onClick={() => void handleSendInviteEmails()}
                    >
                      {inviteSending ? "Sending…" : "Send invite emails"}
                    </button>
                  </div>
                  {inviteSendMessage && (
                    <p className="rp-copy-success">{inviteSendMessage}</p>
                  )}
                </div>
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
        <div className="rp-toolbar">
          <div>
            <h2 className="rp-section-title">Analytics</h2>
          </div>
          <div className="rp-actions">
            <button
              type="button"
              className="rp-secondary rp-btn-compact"
              disabled={exportingSessions}
              onClick={() => void handleExportSessions()}
            >
              {exportingSessions ? "…" : "Sessions CSV"}
            </button>
            <button
              type="button"
              className="rp-secondary rp-btn-compact"
              disabled={exportingAssessments}
              onClick={() => void handleExportAssessments()}
            >
              {exportingAssessments ? "…" : "Assessments CSV"}
            </button>
          </div>
        </div>

        {analyticsLoading && !analytics ? (
          <p className="rp-muted-small rp-loading-inline">Loading analytics…</p>
        ) : analytics ? (
          <>
            <div className="rp-analytics-grid">
              <div className="rp-stat-card">
                <span className="rp-stat-label">Completed</span>
                <strong className="rp-stat-value">{analytics.completed_session_count}</strong>
              </div>
              <div className="rp-stat-card">
                <span className="rp-stat-label">Completion rate</span>
                <strong className="rp-stat-value">
                  {formatPercent(analytics.completion_rate_percent)}
                </strong>
              </div>
              <div className="rp-stat-card">
                <span className="rp-stat-label">Average score</span>
                <strong className="rp-stat-value">
                  {analytics.average_score === null
                    ? "—"
                    : analytics.average_score.toFixed(1)}
                </strong>
              </div>
              <div className="rp-stat-card">
                <span className="rp-stat-label">Integrity flags</span>
                <strong className="rp-stat-value">
                  {formatPercent(analytics.integrity_flag_rate_percent)}
                </strong>
              </div>
              <div className="rp-stat-card">
                <span className="rp-stat-label">Needs review</span>
                <strong className="rp-stat-value">{analytics.review_flagged_count}</strong>
              </div>
              <div className="rp-stat-card">
                <span className="rp-stat-label">Active invites</span>
                <strong className="rp-stat-value">{analytics.invite_count}</strong>
              </div>
            </div>

            <div className="rp-analytics-panels">
              <div className="rp-analytics-panel">
                <h3 className="rp-preview-title">Invite funnel</h3>
                <div className="rp-funnel-list">
                  {(
                    [
                      ["Created", analytics.funnel.created],
                      ["Opened", analytics.funnel.opened],
                      ["Registered", analytics.funnel.registered],
                      ["Verified", analytics.funnel.verified],
                      ["Started", analytics.funnel.started],
                      ["Completed", analytics.funnel.completed],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label} className="rp-funnel-row">
                      <span>{label}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rp-analytics-panel">
                <h3 className="rp-preview-title">Score distribution</h3>
                <div className="rp-distribution-list">
                  {Object.entries(analytics.score_distribution).map(([band, count]) => (
                    <div key={band} className="rp-distribution-row">
                      <span>{band}</span>
                      <strong>{count}</strong>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rp-analytics-panel">
                <h3 className="rp-preview-title">Integrity distribution</h3>
                <div className="rp-distribution-list">
                  {Object.entries(analytics.integrity_distribution).map(([level, count]) => (
                    <div key={level} className="rp-distribution-row">
                      <span>{level.replace(/_/g, " ")}</span>
                      <strong>{count}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {analytics.assessments.length > 0 && (
              <div className="rp-analytics-assessments">
                <h3 className="rp-preview-title">Assessment performance</h3>
                <div className="recruiter-table-wrap">
                  <table className="recruiter-table">
                    <thead>
                      <tr>
                        <th>Role</th>
                        <th>Used</th>
                        <th>Started</th>
                        <th>Completed</th>
                        <th>Avg score</th>
                        <th>Flags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analytics.assessments.map((item) => (
                        <tr key={item.token}>
                          <td>{item.role_preview}</td>
                          <td>{item.used_count}</td>
                          <td>{item.started_count}</td>
                          <td>{item.completed_count}</td>
                          <td>
                            {item.average_score === null
                              ? "—"
                              : item.average_score.toFixed(1)}
                          </td>
                          <td>{item.integrity_flag_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="rp-empty">No analytics yet.</p>
        )}
      </section>

      <section className="rp-card rp-card-wide rp-section">
        <div className="rp-toolbar">
          <div>
            <h2 className="rp-section-title">Interviews</h2>
          </div>
          <div className="rp-actions">
            <button
              type="button"
              className="rp-secondary rp-btn-compact"
              onClick={clearFilters}
            >
              Clear filters
            </button>
            <button
              type="button"
              className="rp-primary rp-btn-compact"
              onClick={applyFilters}
            >
              Apply filters
            </button>
          </div>
        </div>

        <div className="rp-filter-grid">
          <label>
            Role contains
            <input
              type="text"
              value={filterRole}
              onChange={(e) => setFilterRole(e.target.value)}
              placeholder="Backend Engineer"
            />
          </label>
          <label>
            From date
            <input
              type="date"
              value={filterDateFrom}
              onChange={(e) => setFilterDateFrom(e.target.value)}
            />
          </label>
          <label>
            To date
            <input
              type="date"
              value={filterDateTo}
              onChange={(e) => setFilterDateTo(e.target.value)}
            />
          </label>
          <label>
            Assessment token
            <input
              type="text"
              value={filterInviteToken}
              onChange={(e) => setFilterInviteToken(e.target.value)}
              placeholder="Invite UUID"
            />
          </label>
          <label>
            Score band
            <select
              value={filterScoreBand}
              onChange={(e) => setFilterScoreBand(e.target.value)}
            >
              <option value="">Any</option>
              {SCORE_BAND_OPTIONS.map((band) => (
                <option key={band} value={band}>
                  {band}
                </option>
              ))}
            </select>
          </label>
          <label>
            Integrity level
            <select
              value={filterIntegrity}
              onChange={(e) => setFilterIntegrity(e.target.value)}
            >
              <option value="">Any</option>
              {INTEGRITY_OPTIONS.map((level) => (
                <option key={level} value={level}>
                  {level.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </label>
          <label>
            Review status
            <select
              value={filterReviewStatus}
              onChange={(e) => setFilterReviewStatus(e.target.value)}
            >
              <option value="">Any</option>
              {REVIEW_STATUS_OPTIONS.map((status) => (
                <option key={status} value={status}>
                  {formatReviewStatus(status)}
                </option>
              ))}
            </select>
          </label>
        </div>

        <p className="rp-section-desc">Select a row for transcript &amp; proctoring.</p>

        {loading && sessions.length === 0 ? (
          <p className="rp-muted-small rp-loading-inline">Loading…</p>
        ) : sessions.length === 0 ? (
          <p className="rp-empty">No completed interviews yet.</p>
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
                      <div className="rp-review-cell">
                        <span className={reviewBadgeClass(row.review_status)}>
                          {formatReviewStatus(row.review_status)}
                        </span>
                        {(row.human_review_flag || row.low_identity_confidence) && (
                          <div className="rp-row-signals">
                            {row.low_identity_confidence && (
                              <span className="rp-signal-chip">Identity</span>
                            )}
                            {row.integrity_event_count > 0 && (
                              <span className="rp-signal-chip">
                                {row.integrity_event_count} event
                                {row.integrity_event_count === 1 ? "" : "s"}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
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
                  This session still needs recruiter attention.
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

              <section className="rp-evidence-grid">
                <div className="rp-evidence-card">
                  <h3 className="rp-preview-title">Review</h3>
                  <div className="rp-review-status-row">
                    <span className={reviewBadgeClass(detail.review_state.review_status)}>
                      {formatReviewStatus(detail.review_state.review_status)}
                    </span>
                    {detail.review_state.reviewed_at && (
                      <span className="rp-muted-small">
                        Updated {formatDate(detail.review_state.reviewed_at)}
                      </span>
                    )}
                  </div>
                  <label htmlFor="review-notes">Reviewer notes</label>
                  <textarea
                    id="review-notes"
                    value={reviewNotesDraft}
                    onChange={(e) => setReviewNotesDraft(e.target.value)}
                    rows={4}
                    placeholder="Notes for clear / escalate / reject"
                    disabled={reviewUpdating}
                  />
                  <div className="rp-actions">
                    <button
                      type="button"
                      className="rp-secondary"
                      disabled={reviewUpdating}
                      onClick={() => void handleUpdateReviewState("in_review")}
                    >
                      Mark in review
                    </button>
                    <button
                      type="button"
                      className="rp-secondary"
                      disabled={reviewUpdating}
                      onClick={() => void handleUpdateReviewState("escalated")}
                    >
                      Escalate
                    </button>
                    <button
                      type="button"
                      className="rp-secondary"
                      disabled={reviewUpdating}
                      onClick={() => void handleUpdateReviewState("rejected")}
                    >
                      Reject
                    </button>
                    <button
                      type="button"
                      className="rp-primary rp-btn-inline"
                      disabled={reviewUpdating}
                      onClick={() => void handleUpdateReviewState("cleared")}
                    >
                      {reviewUpdating ? "Saving…" : "Clear for decision"}
                    </button>
                  </div>
                </div>

                <div className="rp-evidence-card">
                  <h3 className="rp-preview-title">Identity verification</h3>
                  {detail.identity_verification ? (
                    <div className="rp-evidence-list">
                      <p>
                        Match score:{" "}
                        <strong>
                          {detail.identity_verification.similarity_score != null
                            ? detail.identity_verification.similarity_score.toFixed(2)
                            : "—"}
                        </strong>
                      </p>
                      <p>
                        Liveness:{" "}
                        <strong>
                          {detail.identity_verification.liveness_confidence != null
                            ? detail.identity_verification.liveness_confidence.toFixed(2)
                            : "—"}
                        </strong>
                      </p>
                      <p>
                        OCR name match:{" "}
                        <strong>
                          {detail.identity_verification.ocr_name_match == null
                            ? "—"
                            : detail.identity_verification.ocr_name_match
                              ? "Yes"
                              : "No"}
                        </strong>
                      </p>
                      {detail.identity_verification.message && (
                        <p>{detail.identity_verification.message}</p>
                      )}
                      {detail.identity_verification.warnings.length > 0 && (
                        <ul className="summary-violations-list">
                          {detail.identity_verification.warnings.map((warning, idx) => (
                            <li key={idx}>{warning}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ) : (
                    <p className="rp-muted-small">
                      No structured identity verification evidence was recorded for this session.
                    </p>
                  )}
                </div>
              </section>

              {detail.proctor_events.length > 0 && (
                  <section className="rp-violations-panel">
                    <h3 className="rp-preview-title">Proctor event timeline</h3>
                    <ul className="summary-violations-list">
                      {detail.proctor_events.map((v, idx) => (
                        <li key={`${v.time}-${idx}`}>
                          {new Date(v.time * 1000).toLocaleTimeString()} ·{" "}
                          {formatViolationType(v.type)} ({v.severity}) · −
                          {v.penalty_percent}%{v.message ? ` · ${v.message}` : ""}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

              <div className="rp-transcript">
                {detail.adaptive_interview?.enabled && (
                  <p className="rp-cell-muted" style={{ marginBottom: "0.75rem" }}>
                    Adaptive interview · {detail.adaptive_interview.adaptation_count ?? 0} follow-up
                    {(detail.adaptive_interview.adaptation_count ?? 0) === 1 ? "" : "s"}
                    {detail.adaptive_interview.current_difficulty
                      ? ` · difficulty ${detail.adaptive_interview.current_difficulty}`
                      : ""}
                  </p>
                )}
                {detail.transcript.map((item) => {
                  const j = item.judgment;
                  return (
                    <div key={item.index} className="summary-item">
                      <h3>
                        Q{item.index}
                        {item.is_adaptive_follow_up ? " · Follow-up" : ""}
                        {item.adaptive_topic ? ` · ${item.adaptive_topic}` : ""}
                      </h3>
                      <p>{item.question}</p>
                      <h3 className="rp-answer-title">Answer</h3>
                      <pre className="answer-text rp-code-answer">
                        {item.answer ?? "(not answered)"}
                      </pre>
                      {j && !j.error && (
                        <div className="summary-feedback">
                          {j.weighted_total != null && (
                            <p className="summary-question-score">
                              Score: <strong>{j.weighted_total}</strong> / 100
                            </p>
                          )}
                          {j.run_summary && (
                            <p className="summary-reasoning">
                              Hidden tests:{" "}
                              <strong>
                                {j.run_summary.passed ?? 0}/
                                {j.run_summary.total ?? 0}
                              </strong>{" "}
                              passed
                              {j.grading_mode
                                ? ` · ${j.grading_mode}`
                                : ""}
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
