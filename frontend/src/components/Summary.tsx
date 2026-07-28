import { useEffect, useRef, useState } from "react";
import { interviewApi } from "../api/client";
import type {
  AnswerJudgment,
  EndInterviewResponse,
  FinalScore,
} from "../types/interview";

interface SummaryProps {
  summary: EndInterviewResponse;
  sessionId?: string;
  inviteToken?: string;
  candidateEmail?: string;
  recordingSaved?: boolean;
  onRestart: () => void;
}

function overallScore(final: FinalScore | null | undefined): number | null {
  if (!final) return null;
  const score = final.final_score ?? final.candidate_score;
  return typeof score === "number" ? score : null;
}

function formatIntegrityLevel(level: string | null | undefined): string {
  if (!level) return "Clean";
  return level
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function getJudgment(
  judgments: AnswerJudgment[] | null | undefined,
  index: number,
): AnswerJudgment | null {
  if (!judgments || index >= judgments.length) return null;
  const j = judgments[index];
  if (!j || j.error) return j ?? null;
  return j;
}

export default function Summary({
  summary,
  sessionId: sessionIdProp,
  inviteToken,
  candidateEmail,
  recordingSaved,
  onRestart,
}: SummaryProps) {
  const effectiveSessionId = sessionIdProp ?? summary.session_id;
  const final = summary.final_score;
  const displayScore =
    summary.adjusted_final_score ?? overallScore(final);
  const penalty = summary.integrity_penalty_percent ?? 0;

  const [recordingStatus, setRecordingStatus] = useState<
    "loading" | "available" | "pending" | "unavailable"
  >("loading");
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const [recordingMediaType, setRecordingMediaType] = useState("video/mp4");
  const [downloadingReport, setDownloadingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const recordingUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    const maxAttempts = 6;

    const loadRecording = async () => {
      if (cancelled || !effectiveSessionId) return;
      attempts += 1;
      setRecordingStatus(attempts === 1 ? "loading" : "pending");

      try {
        const blob = await interviewApi.getMyRecording(
          effectiveSessionId,
          inviteToken,
        );
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        recordingUrlRef.current = url;
        setRecordingUrl(url);
        const mediaType = blob.type || "video/mp4";
        setRecordingMediaType(
          mediaType.includes("webm") ? "video/webm" : "video/mp4",
        );
        setRecordingStatus("available");
      } catch {
        if (cancelled) return;
        if (attempts < maxAttempts) {
          setRecordingStatus("pending");
          retryTimer = setTimeout(() => {
            void loadRecording();
          }, 5000);
        } else {
          setRecordingStatus("unavailable");
          setRecordingUrl(null);
        }
      }
    };

    void loadRecording();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      if (recordingUrlRef.current) {
        URL.revokeObjectURL(recordingUrlRef.current);
        recordingUrlRef.current = null;
      }
    };
  }, [effectiveSessionId, inviteToken]);

  async function handleDownloadReport() {
    setDownloadingReport(true);
    setReportError(null);
    try {
      const blob = await interviewApi.downloadMyReport(
        effectiveSessionId,
        inviteToken,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `my-interview-report-${effectiveSessionId.slice(0, 8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setReportError(
        err instanceof Error ? err.message : "Failed to download report",
      );
    } finally {
      setDownloadingReport(false);
    }
  }

  return (
    <div className="card hero-card">
      <div className="alert success">{summary.message}</div>

      {summary.candidate_report_email_sent && candidateEmail && (
        <div className="alert info" style={{ marginTop: "0.75rem" }}>
          A copy of your report has been sent to{" "}
          <strong>{candidateEmail}</strong>.
        </div>
      )}

      {recordingSaved && (
        <div className="alert success" style={{ marginTop: "0.75rem" }}>
          Recording saved.
        </div>
      )}

      <section className="summary-overall">
        <h2>Results</h2>
        {displayScore !== null && (
          <p className="summary-score">
            Score: <strong>{displayScore}</strong>
            <span className="summary-score-max"> / 100</span>
          </p>
        )}
        <p className="summary-integrity-level">
          Integrity:{" "}
          <strong>{formatIntegrityLevel(summary.integrity_level)}</strong>
        </p>
        {penalty > 0 && (
          <p className="summary-penalty">
            Penalty: <strong>-{penalty}%</strong>
          </p>
        )}
      </section>

      {summary.questions.map((q, i) => {
        const judgment = getJudgment(summary.answer_judgments, i);

        return (
          <div key={i} className="summary-item">
            <h3>Question {i + 1}</h3>
            <p>{q}</p>

            {judgment?.error === "judging_failed" && (
              <div className="alert info" style={{ marginTop: "0.75rem" }}>
                Feedback could not be generated for this answer.
              </div>
            )}

            {judgment && !judgment.error && (
              <div className="summary-feedback">
                {judgment.strengths && judgment.strengths.length > 0 && (
                  <div className="summary-feedback-block">
                    <h4>Strengths</h4>
                    <ul>
                      {judgment.strengths.map((s, idx) => (
                        <li key={idx}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {judgment.improvements && judgment.improvements.length > 0 && (
                  <div className="summary-feedback-block">
                    <h4>Areas to improve</h4>
                    <ul>
                      {judgment.improvements.map((s, idx) => (
                        <li key={idx}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      <section className="summary-recording summary-recording-card">
        <h2>Recording</h2>
        {recordingStatus === "loading" && (
          <p className="summary-recording-note">Checking recording…</p>
        )}
        {recordingStatus === "available" && recordingUrl && (
          <>
            <video className="summary-recording-video" controls width="100%" playsInline>
              <source src={recordingUrl} type={recordingMediaType} />
              Your browser does not support video playback.
            </video>
            <p className="summary-recording-note">
              For your personal review only
            </p>
          </>
        )}
        {recordingStatus === "pending" && (
          <p className="summary-recording-note">
            Uploading recording…
          </p>
        )}
        {recordingStatus === "unavailable" && (
          <p className="summary-recording-note">
            Recording is not available. If you just finished, check the browser
            console for [RECORDING] logs and try refreshing this page.
          </p>
        )}
      </section>

      <section className="summary-report-download">
        {reportError && (
          <div className="alert error" style={{ marginBottom: "1rem" }}>
            {reportError}
          </div>
        )}
        <button
          type="button"
          className="summary-download-report"
          onClick={handleDownloadReport}
          disabled={downloadingReport}
        >
          {downloadingReport
            ? "Preparing your report…"
            : "Download My Interview Report"}
        </button>
        <p className="summary-report-note">
          This report contains your personal feedback and is for your reference only
        </p>
      </section>

      <div className="actions" style={{ marginTop: "1.5rem" }}>
        <button type="button" className="primary" onClick={onRestart}>
          Start New Interview
        </button>
      </div>
    </div>
  );
}
