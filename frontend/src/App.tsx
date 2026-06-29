import { useEffect, useRef, useState } from "react";
import {
  authApi,
  interviewApi,
  loadStoredRefreshToken,
  setAccessToken,
  setOnUnauthorized,
  setRefreshToken,
} from "./api/client";
import Auth from "./components/Auth";
import VerifyEmail from "./components/VerifyEmail";
import ResetPassword from "./components/ResetPassword";
import InterviewRoom, { type InterviewRoomHandle } from "./components/InterviewRoom";
import RecruiterDashboard from "./components/RecruiterDashboard";
import RecruiterLogin from "./components/RecruiterLogin";
import PrivacyPolicy from "./components/PrivacyPolicy";
import CandidateInviteFlow from "./components/CandidateInviteFlow";
import PreInterviewChecklist from "./components/PreInterviewChecklist";
import SetupForm from "./components/SetupForm";
import Summary from "./components/Summary";
import MobileBlock from "./components/MobileBlock";
import ErrorPage from "./components/ErrorPage";
import type { UserResponse } from "./types/auth";
import type {
  CurrentQuestionResponse,
  EndInterviewResponse,
} from "./types/interview";
import { isMobileDevice } from "./utils/deviceCheck";

type AppPhase = "setup" | "checklist" | "interview" | "summary";

function normalizePathname(path: string): string {
  const cleaned = path.replace(/\/+$/, "") || "/";
  return cleaned.replace(/\/{2,}/g, "/") || "/";
}

function useAppPathname(): string {
  const [pathname, setPathname] = useState(() =>
    normalizePathname(window.location.pathname),
  );

  useEffect(() => {
    const onPopState = () => {
      setPathname(normalizePathname(window.location.pathname));
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  return pathname;
}

const REGISTER_VERIFY_NOTICE_KEY = "ss_register_verify_notice";
const DISMISS_REGISTER_VERIFY_KEY = "ss_dismiss_register_verify";
const PASSWORD_RESET_DONE_KEY = "ss_password_reset_done";

function RecruiterDashboardRoute() {
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      loadStoredRefreshToken();
      const refresh = loadStoredRefreshToken();
      try {
        if (refresh) {
          const tokens = await authApi.refresh(refresh);
          setAccessToken(tokens.data.access_token);
          setRefreshToken(tokens.data.refresh_token);
        }
        const me = await authApi.me();
        if (me.data.role !== "recruiter") {
          window.location.href = "/recruiter";
          return;
        }
        if (!cancelled) {
          setReady(true);
        }
      } catch {
        if (!cancelled) {
          window.location.href = "/recruiter";
        }
      }
    }

    void boot();
    return () => {
      cancelled = true;
    };
  }, []);

  function handleLogout() {
    setAccessToken(null);
    setRefreshToken(null);
    window.location.href = "/recruiter";
  }

  if (!ready) {
    return (
      <div className="app">
        <div className="card loading">Loading recruiter dashboard…</div>
      </div>
    );
  }

  return (
    <div className="app">
      {error && <div className="alert error">{error}</div>}
      <RecruiterDashboard
        loading={loading}
        onLoadingChange={setLoading}
        onError={setError}
        onLogout={handleLogout}
      />
    </div>
  );
}

export default function App() {
  const pathname = useAppPathname();

  if (pathname === "/privacy") {
    return (
      <div className="app">
        <PrivacyPolicy />
      </div>
    );
  }

  if (pathname === "/verify-email") {
    return <VerifyEmail />;
  }

  if (pathname === "/reset-password") {
    return <ResetPassword />;
  }

  if (pathname === "/recruiter") {
    return (
      <div className="app">
        <RecruiterLogin />
      </div>
    );
  }

  if (pathname === "/recruiter/dashboard") {
    return <RecruiterDashboardRoute />;
  }

  if (pathname.startsWith("/interview/invite/")) {
    const inviteToken = decodeURIComponent(
      pathname.slice("/interview/invite/".length),
    );
    if (inviteToken) {
      return (
        <div className="app">
          <CandidateInviteFlow token={inviteToken} />
        </div>
      );
    }
  }

  const [accessToken, setAccessTokenState] = useState<string | null>(null);
  const [user, setUser] = useState<UserResponse | null>(null);
  const [phase, setPhase] = useState<AppPhase>("setup");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverError, setServerError] = useState(false);
  const [registerVerificationNotice, setRegisterVerificationNotice] = useState(
    () =>
      sessionStorage.getItem(REGISTER_VERIFY_NOTICE_KEY) === "1" &&
      sessionStorage.getItem(DISMISS_REGISTER_VERIFY_KEY) !== "1" &&
      sessionStorage.getItem(PASSWORD_RESET_DONE_KEY) !== "1",
  );
  const [resendStatus, setResendStatus] = useState<string | null>(null);
  const [resendLoading, setResendLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentQuestion, setCurrentQuestion] =
    useState<CurrentQuestionResponse | null>(null);
  const [summary, setSummary] = useState<EndInterviewResponse | null>(null);
  const [recordingSaved, setRecordingSaved] = useState(false);
  const [mobileBlocked] = useState(() => isMobileDevice());
  const [interviewMediaStream, setInterviewMediaStream] =
    useState<MediaStream | null>(null);
  const interviewRoomRef = useRef<InterviewRoomHandle>(null);

  function releaseInterviewMediaStream() {
    setInterviewMediaStream((current) => {
      current?.getTracks().forEach((t) => t.stop());
      return null;
    });
  }

  useEffect(() => {
    setAccessToken(accessToken);
  }, [accessToken]);

  useEffect(() => {
    setOnUnauthorized(() => {
      setAccessTokenState(null);
      setUser(null);
      setRefreshToken(null);
      setPhase("setup");
      setSessionId(null);
      setCurrentQuestion(null);
      setSummary(null);
      setError("Your session expired. Please log in again.");
    });
    return () => setOnUnauthorized(null);
  }, []);

  function handleAuthenticated(payload: {
    accessToken: string;
    refreshToken: string;
    user: UserResponse;
    justRegistered?: boolean;
  }) {
    setAccessTokenState(payload.accessToken);
    setRefreshToken(payload.refreshToken);
    setUser(payload.user);
    setResendStatus(null);
    setError(null);
    setServerError(false);

    const afterPasswordReset =
      sessionStorage.getItem(PASSWORD_RESET_DONE_KEY) === "1";
    if (afterPasswordReset) {
      sessionStorage.removeItem(PASSWORD_RESET_DONE_KEY);
      sessionStorage.removeItem(REGISTER_VERIFY_NOTICE_KEY);
      sessionStorage.setItem(DISMISS_REGISTER_VERIFY_KEY, "1");
      setRegisterVerificationNotice(false);
      return;
    }

    if (payload.justRegistered) {
      sessionStorage.setItem(REGISTER_VERIFY_NOTICE_KEY, "1");
      sessionStorage.removeItem(DISMISS_REGISTER_VERIFY_KEY);
      setRegisterVerificationNotice(true);
      return;
    }

    setRegisterVerificationNotice(
      sessionStorage.getItem(REGISTER_VERIFY_NOTICE_KEY) === "1" &&
        sessionStorage.getItem(DISMISS_REGISTER_VERIFY_KEY) !== "1",
    );
  }

  function dismissRegisterVerificationNotice() {
    sessionStorage.setItem(DISMISS_REGISTER_VERIFY_KEY, "1");
    setRegisterVerificationNotice(false);
    setResendStatus(null);
  }

  async function handleResendVerification() {
    if (!user?.email) return;
    setResendLoading(true);
    setResendStatus(null);
    try {
      const result = await authApi.resendVerification(user.email);
      setResendStatus(result.message);
      dismissRegisterVerificationNotice();
    } catch (err) {
      setResendStatus(
        err instanceof Error ? err.message : "Failed to send verification email",
      );
    } finally {
      setResendLoading(false);
    }
  }

  function handleLogout() {
    releaseInterviewMediaStream();
    setAccessTokenState(null);
    setRefreshToken(null);
    setUser(null);
    setPhase("setup");
    setSessionId(null);
    setCurrentQuestion(null);
    setSummary(null);
    setRecordingSaved(false);
    sessionStorage.removeItem(REGISTER_VERIFY_NOTICE_KEY);
    sessionStorage.removeItem(DISMISS_REGISTER_VERIFY_KEY);
    setRegisterVerificationNotice(false);
    setResendStatus(null);
    setError(null);
    setServerError(false);
  }

  async function finishInterview() {
    if (!sessionId) return;
    let uploaded = false;
    try {
      console.log("[RECORDING] finishInterview: stopping and uploading…");
      const result = await interviewRoomRef.current?.stopAndUploadRecording();
      uploaded = result?.uploaded ?? false;
      console.log("[RECORDING] finishInterview: upload complete, uploaded:", uploaded);
    } catch (err) {
      console.error("[RECORDING] finishInterview: upload error:", err);
      uploaded = false;
    }
    const ended = await interviewApi.endInterview(sessionId);
    setRecordingSaved(uploaded);
    setSummary(ended);
    releaseInterviewMediaStream();
    setPhase("summary");
  }

  async function handleStart(data: {
    role_title: string;
    experience_level: string;
    topic_focus: string;
    question_count: number;
    job_description: string;
    job_description_pdf: File | null;
    resume_pdf: File | null;
  }) {
    setLoading(true);
    setError(null);
    setServerError(false);
    try {
      if (!data.resume_pdf) {
        throw new Error(
          "Please upload a resume (PDF, Word, or TXT) before starting the interview.",
        );
      }

      const formData = new FormData();
      formData.append("role_title", data.role_title);
      formData.append("experience_level", data.experience_level);
      if (data.topic_focus.trim()) {
        formData.append("topic_focus", data.topic_focus.trim());
      }
      formData.append("job_description", data.job_description);
      if (data.job_description_pdf) {
        formData.append("job_description_pdf", data.job_description_pdf);
      }
      formData.append("resume_pdf", data.resume_pdf);

      const session = await interviewApi.createSession(formData);
      setSessionId(session.session_id);

      await interviewApi.generateQuestions(
        session.session_id,
        data.question_count,
      );

      setPhase("checklist");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to start interview";
      setError(message);
      if (message.includes("server") || message.includes("unavailable")) {
        setServerError(true);
      }
      throw err;
    } finally {
      setLoading(false);
    }
  }

  async function handleChecklistReady(mediaStream: MediaStream) {
    if (!sessionId) return;
    setInterviewMediaStream(mediaStream);
    setLoading(true);
    setError(null);
    try {
      const question = await interviewApi.getCurrentQuestion(sessionId);
      setCurrentQuestion(question);
      setPhase("interview");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load first question",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitAnswer(answer: string) {
    if (!sessionId || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await interviewApi.submitAnswer(sessionId, answer);

      if (result.is_complete) {
        await finishInterview();
        return;
      }

      const next = await interviewApi.getCurrentQuestion(sessionId);
      setCurrentQuestion(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit answer");
    } finally {
      setLoading(false);
    }
  }

  async function handleEndEarly() {
    if (!sessionId || loading) return;
    const remaining = currentQuestion
      ? currentQuestion.total_questions - currentQuestion.question_index
      : 0;
    const ok = window.confirm(
      remaining > 0
        ? `You have ${remaining} unanswered question(s). End anyway?`
        : "End this interview?",
    );
    if (!ok) return;

    setLoading(true);
    setError(null);
    try {
      await finishInterview();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to end interview");
    } finally {
      setLoading(false);
    }
  }

  async function handleIdleTimeout() {
    if (!sessionId || loading) return;
    setError("Interview ended due to inactivity (15 minutes). Your progress has been saved.");
    setLoading(true);
    try {
      await finishInterview();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to end interview");
    } finally {
      setLoading(false);
    }
  }

  function handleRestart() {
    releaseInterviewMediaStream();
    setPhase("setup");
    setSessionId(null);
    setCurrentQuestion(null);
    setSummary(null);
    setRecordingSaved(false);
    setError(null);
    setServerError(false);
  }

  const isLoggedIn = accessToken !== null;
  const isRecruiter = user?.role === "recruiter";
  const needsEmailVerification =
    isLoggedIn && user?.role === "candidate" && user.is_verified === false;

  if (serverError && !isLoggedIn) {
    return (
      <div className="app">
        <ErrorPage
          code={500}
          message={error ?? undefined}
          onRetry={() => {
            setServerError(false);
            setError(null);
          }}
        />
      </div>
    );
  }

  return (
    <div className="app">
      <header>
        <h1>AI Interview Engine</h1>
        <p>
          {isRecruiter
            ? "Recruiter dashboard — review completed interviews."
            : "Technical interviews powered by AI — one question at a time."}
        </p>
        {isLoggedIn && (
          <button
            type="button"
            className="secondary"
            onClick={handleLogout}
            disabled={loading}
            style={{ marginTop: "0.75rem" }}
          >
            Log out
          </button>
        )}
      </header>

      {error && <div className="alert error">{error}</div>}

      {registerVerificationNotice && (
        <div className="alert warning">
          Account created! Please check your email to verify your account.{" "}
          <button
            type="button"
            className="link-button"
            onClick={() => void handleResendVerification()}
            disabled={resendLoading}
          >
            {resendLoading ? "Sending…" : "Resend verification email"}
          </button>
          <button
            type="button"
            className="link-button"
            onClick={dismissRegisterVerificationNotice}
            style={{ marginLeft: "0.75rem" }}
          >
            Dismiss
          </button>
          {resendStatus && (
            <span style={{ display: "block", marginTop: "0.5rem" }}>
              {resendStatus}
            </span>
          )}
        </div>
      )}

      {!isLoggedIn ? (
        <>
          <div className="card hero-card" style={{ marginBottom: "1.25rem" }}>
            <div className="pill" style={{ marginBottom: "1rem" }}>AI-led mock interviews</div>
            <h2 className="section-title">Practice and evaluate technical interviews in a premium, focused workspace.</h2>
            <p className="section-subtitle">
              Upload your resume, tailor the role context, complete a proctored interview, and review structured feedback and recordings.
            </p>
          </div>
          <Auth
            loading={loading}
            onLoadingChange={setLoading}
            onError={setError}
            onAuthenticated={handleAuthenticated}
          />
        </>
      ) : isRecruiter ? (
        <RecruiterDashboard
          loading={loading}
          onLoadingChange={setLoading}
          onError={setError}
        />
      ) : mobileBlocked ? (
        <MobileBlock />
      ) : needsEmailVerification ? (
        <div className="card status-panel">
          <h2 className="section-title">Verify your email</h2>
          <p className="invite-meta">
            Please verify your email before starting an interview. We sent a
            link to <strong>{user?.email}</strong>.
          </p>
          <button
            type="button"
            className="primary"
            onClick={() => void handleResendVerification()}
            disabled={resendLoading}
          >
            {resendLoading ? "Sending…" : "Resend verification email"}
          </button>
          {resendStatus && (
            <p className="invite-meta" style={{ marginTop: "1rem" }}>
              {resendStatus}
            </p>
          )}
        </div>
      ) : (
        <>
          {phase === "setup" && (
            <SetupForm loading={loading} onStart={handleStart} />
          )}

          {phase === "checklist" && sessionId && (
            <PreInterviewChecklist
              sessionId={sessionId}
              onReady={handleChecklistReady}
              loading={loading}
            />
          )}

          {phase === "interview" && sessionId && currentQuestion && (
            <>
              {!currentQuestion.is_complete && currentQuestion.question ? (
                <InterviewRoom
                  ref={interviewRoomRef}
                  sessionId={sessionId}
                  mediaStream={interviewMediaStream}
                  question={currentQuestion}
                  loading={loading}
                  onSubmitAnswer={handleSubmitAnswer}
                  onEndEarly={handleEndEarly}
                  onIdleTimeout={handleIdleTimeout}
                />
              ) : (
                <div className="card loading">Loading next question…</div>
              )}
            </>
          )}

          {phase === "summary" && summary && (
            <Summary
              summary={summary}
              candidateEmail={user?.email}
              recordingSaved={recordingSaved}
              onRestart={handleRestart}
            />
          )}
        </>
      )}
    </div>
  );
}

