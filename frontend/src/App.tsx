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
import JobApplyPage from "./components/JobApplyPage";
import LiveInterviewRoom from "./components/LiveInterviewRoom";
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
      <div className="recruiter-portal">
        <div className="rp-card loading">Loading recruiter dashboard…</div>
      </div>
    );
  }

  return (
    <>
      {error && (
        <div className="recruiter-portal" style={{ paddingBottom: 0 }}>
          <div className="rp-alert error" style={{ maxWidth: 960, margin: "0 auto 0.75rem" }}>
            {error}
          </div>
        </div>
      )}
      <RecruiterDashboard
        loading={loading}
        onLoadingChange={setLoading}
        onError={setError}
        onLogout={handleLogout}
      />
    </>
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

  if (pathname.startsWith("/apply/")) {
    const jobToken = decodeURIComponent(pathname.slice("/apply/".length));
    if (jobToken) {
      return (
        <div className="app">
          <JobApplyPage token={jobToken} />
        </div>
      );
    }
  }

  if (pathname.startsWith("/live/")) {
    const rest = pathname.slice("/live/".length);
    const roomToken = decodeURIComponent(rest.split("?")[0] || rest);
    const params = new URLSearchParams(window.location.search);
    const role =
      params.get("role") === "recruiter" ? "recruiter" : "candidate";
    const displayName = params.get("name") || undefined;
    if (roomToken) {
      return (
        <div className="app app-live-room">
          <LiveInterviewRoom
            token={roomToken}
            role={role}
            displayName={displayName}
          />
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
  const [devVerificationUrl, setDevVerificationUrl] = useState<string | null>(null);
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
    verificationUrl?: string | null;
    emailNote?: string | null;
    registerMessage?: string | null;
  }) {
    setAccessTokenState(payload.accessToken);
    setRefreshToken(payload.refreshToken);
    setUser(payload.user);
    setResendStatus(null);
    setError(null);
    setServerError(false);
    setDevVerificationUrl(payload.verificationUrl ?? null);

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
      if (payload.emailNote || payload.registerMessage?.toLowerCase().includes("could not send")) {
        setError(
          payload.emailNote ||
            payload.registerMessage ||
            "Account created, but we could not send the verification email.",
        );
      }
      return;
    }

    setRegisterVerificationNotice(
      sessionStorage.getItem(REGISTER_VERIFY_NOTICE_KEY) === "1" &&
        sessionStorage.getItem(DISMISS_REGISTER_VERIFY_KEY) !== "1",
    );
  }

  async function handleResendVerification() {
    if (!user?.email) return;
    setResendLoading(true);
    setResendStatus(null);
    try {
      const result = await authApi.resendVerification(user.email);
      setResendStatus(result.message);
      if (result.verification_url) {
        setDevVerificationUrl(result.verification_url);
      }
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
    setDevVerificationUrl(null);
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

  async function handleSubmitCodingAnswer(language: string, source: string) {
    if (!sessionId || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await interviewApi.submitCodingAnswer(
        sessionId,
        language,
        source,
      );
      if (result.is_complete) {
        await finishInterview();
        return;
      }
      const next = await interviewApi.getCurrentQuestion(sessionId);
      setCurrentQuestion(next);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to submit coding answer",
      );
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

  useEffect(() => {
    if (!accessToken || !user) return;
    if (user.role === "recruiter") {
      window.location.replace("/recruiter/dashboard");
    }
  }, [accessToken, user]);

  const isLoggedIn = accessToken !== null;
  const isRecruiter = user?.role === "recruiter";
  const needsEmailVerification =
    isLoggedIn && user?.role === "candidate" && user.is_verified === false;

  useEffect(() => {
    if (!accessToken || user?.role !== "candidate" || user.is_verified !== false) {
      return;
    }

    let cancelled = false;

    async function syncVerificationStatus() {
      try {
        const me = await authApi.me();
        if (cancelled || !me.data.is_verified) return;
        setUser(me.data);
        sessionStorage.removeItem(REGISTER_VERIFY_NOTICE_KEY);
        sessionStorage.setItem(DISMISS_REGISTER_VERIFY_KEY, "1");
        setRegisterVerificationNotice(false);
        setDevVerificationUrl(null);
        setResendStatus(null);
      } catch {
        /* ignore transient errors while polling */
      }
    }

    void syncVerificationStatus();

    const onResume = () => void syncVerificationStatus();
    window.addEventListener("focus", onResume);
    document.addEventListener("visibilitychange", onResume);
    const intervalId = window.setInterval(() => void syncVerificationStatus(), 5000);

    return () => {
      cancelled = true;
      window.removeEventListener("focus", onResume);
      document.removeEventListener("visibilitychange", onResume);
      window.clearInterval(intervalId);
    };
  }, [accessToken, user?.role, user?.is_verified]);

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
        <h1>AI Interview Bot</h1>
        <p>
          {isRecruiter
            ? "Create assessments and review interviews."
            : "Proctored technical interviews, one question at a time."}
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
          <p>
            {devVerificationUrl && error
              ? "We could not send the verification email. Use the link below, or try Resend."
              : "Check your inbox for a verification link — this page updates after you verify."}
          </p>
          <button
            type="button"
            className="link-button"
            onClick={() => void handleResendVerification()}
            disabled={resendLoading}
            style={{ marginTop: "0.5rem" }}
          >
            {resendLoading ? "Sending…" : "Resend verification email"}
          </button>
          {devVerificationUrl && (
            <p className="invite-meta" style={{ marginTop: "0.75rem", wordBreak: "break-all" }}>
              {error ? "Verification link: " : "Local dev link: "}
              <a href={devVerificationUrl}>{devVerificationUrl}</a>
            </p>
          )}
          {resendStatus && (
            <span style={{ display: "block", marginTop: "0.5rem" }}>
              {resendStatus}
            </span>
          )}
        </div>
      )}

      {!isLoggedIn ? (
        <Auth
          loading={loading}
          onLoadingChange={setLoading}
          onError={setError}
          onAuthenticated={handleAuthenticated}
        />
      ) : isRecruiter ? (
        <div className="card status-panel">
          <h2 className="section-title">Recruiter portal</h2>
          <p className="invite-meta">
            Assessments, ATS jobs, and live interviews live in the recruiter dashboard.
          </p>
          <div className="actions" style={{ marginTop: "1rem" }}>
            <a
              href="/recruiter/dashboard"
              className="primary"
              style={{ textDecoration: "none" }}
            >
              Open dashboard
            </a>
          </div>
        </div>
      ) : mobileBlocked ? (
        <MobileBlock />
      ) : needsEmailVerification ? (
        <div className="card status-panel">
          <h2 className="section-title">Verify your email</h2>
          <p className="invite-meta">
            Open the link sent to <strong>{user?.email}</strong> — this page unlocks automatically.
          </p>
          <button
            type="button"
            className="primary"
            style={{ marginTop: "1rem" }}
            onClick={() => void handleResendVerification()}
            disabled={resendLoading}
          >
            {resendLoading ? "Sending…" : "Resend verification email"}
          </button>
          {devVerificationUrl && (
            <p className="invite-meta" style={{ marginTop: "1rem", wordBreak: "break-all" }}>
              Local dev — click to verify:{" "}
              <a href={devVerificationUrl}>{devVerificationUrl}</a>
            </p>
          )}
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
                  onSubmitCodingAnswer={handleSubmitCodingAnswer}
                  onEndEarly={handleEndEarly}
                  onIdleTimeout={handleIdleTimeout}
                  candidateEmail={user?.email}
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

