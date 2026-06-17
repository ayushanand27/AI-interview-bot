import { useRef, useState } from "react";
import { interviewApi } from "../api/client";

const DOCUMENT_ACCEPT =
  ".pdf,.doc,.docx,.txt,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";

type JdInputMode = "paste" | "pdf";

export type SetupFormData = {
  role_title: string;
  experience_level: string;
  topic_focus: string;
  question_count: number;
  job_description: string;
  job_description_pdf: File | null;
  resume_pdf: File | null;
};

interface SetupFormProps {
  loading: boolean;
  onStart: (data: SetupFormData) => Promise<void>;
}

function isActiveInterviewError(message: string): boolean {
  return message.toLowerCase().includes("active interview");
}

export default function SetupForm({ loading, onStart }: SetupFormProps) {
  const [jdMode, setJdMode] = useState<JdInputMode>("paste");
  const [jdError, setJdError] = useState<string | null>(null);
  const [stuckSession, setStuckSession] = useState(false);
  const [clearingStuck, setClearingStuck] = useState(false);
  const pendingStartRef = useRef<SetupFormData | null>(null);

  async function submitInterview(data: SetupFormData) {
    pendingStartRef.current = data;
    setStuckSession(false);
    try {
      await onStart(data);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to start interview";
      if (isActiveInterviewError(message)) {
        setStuckSession(true);
      }
    }
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const job_description = String(form.get("job_description") || "").trim();
    const job_description_pdf =
      (form.get("job_description_pdf") as File | null) ?? null;
    const hasPdf =
      job_description_pdf instanceof File && job_description_pdf.size > 0;

    if (jdMode === "paste" && !job_description) {
      setJdError("Please paste a job description or switch to Upload JD file.");
      return;
    }
    if (jdMode === "pdf" && !hasPdf) {
      setJdError(
        "Please upload a job description file (PDF, Word, or TXT) or switch to Paste JD Text.",
      );
      return;
    }
    setJdError(null);

    void submitInterview({
      role_title: String(form.get("role_title") || "Software Engineer"),
      experience_level: String(form.get("experience_level") || "mid"),
      topic_focus: String(form.get("topic_focus") || ""),
      question_count: Number(form.get("question_count") || 5),
      job_description: jdMode === "paste" ? job_description : "",
      job_description_pdf: jdMode === "pdf" && hasPdf ? job_description_pdf : null,
      resume_pdf: (form.get("resume_pdf") as File | null) ?? null,
    });
  }

  async function handleClearStuckSession() {
    setClearingStuck(true);
    try {
      await interviewApi.resetActiveSession();
      setStuckSession(false);
      if (pendingStartRef.current) {
        await submitInterview(pendingStartRef.current);
      }
    } catch {
      setStuckSession(true);
    } finally {
      setClearingStuck(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2 style={{ marginBottom: "1.25rem", fontSize: "1.15rem" }}>
        Start your interview
      </h2>

      <div className="field">
        <label htmlFor="role_title">Role title</label>
        <input
          id="role_title"
          name="role_title"
          defaultValue="Machine Learning Engineer"
          required
        />
      </div>

      <div className="field">
        <label htmlFor="experience_level">Experience level</label>
        <select id="experience_level" name="experience_level" defaultValue="mid">
          <option value="junior">Junior</option>
          <option value="mid">Mid</option>
          <option value="senior">Senior</option>
        </select>
      </div>

      <div className="field">
        <label htmlFor="topic_focus">Topic focus (optional)</label>
        <input
          id="topic_focus"
          name="topic_focus"
          placeholder="e.g. supervised learning, LLMs"
        />
      </div>

      <div className="field">
        <label>Job description</label>
        <div className="auth-toggle" style={{ marginBottom: "0.75rem" }}>
          <button
            type="button"
            className={jdMode === "paste" ? "primary" : "secondary"}
            onClick={() => {
              setJdMode("paste");
              setJdError(null);
            }}
            disabled={loading || clearingStuck}
          >
            Paste JD Text
          </button>
          <button
            type="button"
            className={jdMode === "pdf" ? "primary" : "secondary"}
            onClick={() => {
              setJdMode("pdf");
              setJdError(null);
            }}
            disabled={loading || clearingStuck}
            style={{ marginLeft: "0.5rem" }}
          >
            Upload JD File
          </button>
        </div>

        {jdMode === "paste" ? (
          <textarea
            id="job_description"
            name="job_description"
            placeholder="Paste the job description here so the interview can be tailored to the role"
            rows={6}
          />
        ) : (
          <input
            id="job_description_pdf"
            name="job_description_pdf"
            type="file"
            accept={DOCUMENT_ACCEPT}
          />
        )}
        {jdError && (
          <div className="alert error" style={{ marginTop: "0.75rem" }}>
            {jdError}
          </div>
        )}
      </div>

      <div className="field">
        <label htmlFor="resume_pdf">
          Resume upload (PDF, Word, or TXT)
        </label>
        <input
          id="resume_pdf"
          name="resume_pdf"
          type="file"
          accept={DOCUMENT_ACCEPT}
          required
        />
      </div>

      <div className="field">
        <label htmlFor="question_count">Number of questions</label>
        <input
          id="question_count"
          name="question_count"
          type="number"
          min={1}
          max={15}
          defaultValue={5}
          required
        />
      </div>

      {stuckSession && (
        <div className="alert warning" style={{ marginBottom: "1rem" }}>
          A previous interview session is still marked as active.
          <button
            type="button"
            className="secondary"
            onClick={() => void handleClearStuckSession()}
            disabled={loading || clearingStuck}
            style={{ display: "block", marginTop: "0.75rem" }}
          >
            {clearingStuck
              ? "Clearing session…"
              : "Clear stuck session and start fresh"}
          </button>
        </div>
      )}

      <button
        type="submit"
        className="primary"
        disabled={loading || clearingStuck}
      >
        {loading ? "Starting…" : "Start interview"}
      </button>
    </form>
  );
}
