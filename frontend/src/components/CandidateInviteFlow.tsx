import { useEffect, useRef, useState } from "react";
import {
  interviewApi,
  inviteApi,
  setAccessToken,
  setRefreshToken,
} from "../api/client";
import InterviewRoom, { type InterviewRoomHandle } from "./InterviewRoom";
import PreInterviewChecklist from "./PreInterviewChecklist";
import Summary from "./Summary";
import type { InviteValidInfo } from "../types/invite";
import { InviteFlowError } from "../types/invite";
import type {
  CurrentQuestionResponse,
  EndInterviewResponse,
} from "../types/interview";
import { pickPreferredCameraDeviceId } from "../hooks/useExtensionDetection";
import "../invite-flow.css";

type InviteStep =
  | "loading"
  | "invalid"
  | "welcome"
  | "details"
  | "identity"
  | "checklist"
  | "interview"
  | "summary";

type DetailsMode = "register" | "login";

type LivenessAction = "center" | "move_left" | "move_right" | "smile";

const LIVENESS_STEPS: Array<{
  action: LivenessAction;
  title: string;
  hint: string;
}> = [
  {
    action: "center",
    title: "1",
    hint: "Face the camera, centered.",
  },
  {
    action: "move_left",
    title: "2",
    hint: "Turn slightly left.",
  },
  {
    action: "move_right",
    title: "3",
    hint: "Turn slightly right.",
  },
  {
    action: "smile",
    title: "4",
    hint: "Smile for the final capture.",
  },
];

interface CandidateInviteFlowProps {
  token: string;
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function CandidateInviteFlow({ token }: CandidateInviteFlowProps) {
  const [step, setStep] = useState<InviteStep>("loading");
  const [inviteInfo, setInviteInfo] = useState<InviteValidInfo | null>(null);
  const [invalidReason, setInvalidReason] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailsMode, setDetailsMode] = useState<DetailsMode>("register");
  const [prefilledEmail, setPrefilledEmail] = useState("");
  const [candidateEmail, setCandidateEmail] = useState("");

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentQuestion, setCurrentQuestion] =
    useState<CurrentQuestionResponse | null>(null);
  const [summary, setSummary] = useState<EndInterviewResponse | null>(null);
  const [recordingSaved, setRecordingSaved] = useState(false);
  const [interviewMediaStream, setInterviewMediaStream] =
    useState<MediaStream | null>(null);
  const interviewRoomRef = useRef<InterviewRoomHandle>(null);

  const [idPreview, setIdPreview] = useState<string | null>(null);
  const [idDataUrl, setIdDataUrl] = useState<string | null>(null);
  const [selfiePreview, setSelfiePreview] = useState<string | null>(null);
  const [selfieDataUrl, setSelfieDataUrl] = useState<string | null>(null);
  const [selfieSequence, setSelfieSequence] = useState<string[]>([]);
  const [livenessStepIndex, setLivenessStepIndex] = useState(0);
  const [verifying, setVerifying] = useState(false);
  const [identityVerified, setIdentityVerified] = useState(false);
  const [verifyMessage, setVerifyMessage] = useState<string | null>(null);
  const [verifyWarnings, setVerifyWarnings] = useState<string[]>([]);

  const videoRef = useRef<HTMLVideoElement>(null);
  const selfieStreamRef = useRef<MediaStream | null>(null);
  const idInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    inviteApi
      .checkInvite(token)
      .then((res) => {
        if (cancelled) return;
        if (res.valid) {
          setInviteInfo(res);
          setStep("welcome");
        } else {
          setInvalidReason(res.reason);
          setStep("invalid");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setInvalidReason(
            err instanceof Error ? err.message : "Unable to validate invite link",
          );
          setStep("invalid");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    return () => {
      selfieStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    if (step !== "identity") return;

    let cancelled = false;
    void (async () => {
      try {
        const preferredId = await pickPreferredCameraDeviceId();
        if (cancelled) return;
        const stream = await navigator.mediaDevices.getUserMedia({
          video: preferredId
            ? { deviceId: { ideal: preferredId }, facingMode: "user" }
            : { facingMode: "user" },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        selfieStreamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      } catch (err) {
        if (!cancelled) {
          const insecure = !window.isSecureContext;
          setError(
            insecure
              ? "Webcam requires HTTPS or localhost. Open http://127.0.0.1:5173 (not your LAN IP) for local testing."
              : err instanceof Error
                ? err.message
                : "Could not access webcam for selfie capture.",
          );
        }
      }
    })();

    return () => {
      cancelled = true;
      selfieStreamRef.current?.getTracks().forEach((t) => t.stop());
      selfieStreamRef.current = null;
    };
  }, [step]);

  function releaseInterviewMediaStream() {
    setInterviewMediaStream((current) => {
      current?.getTracks().forEach((t) => t.stop());
      return null;
    });
  }

  async function attachToInterview(
    res: { data: { access_token: string; refresh_token: string; session_id: string } },
  ) {
    setAccessToken(res.data.access_token);
    setRefreshToken(res.data.refresh_token);
    setSessionId(res.data.session_id);
    setStep("identity");
  }

  async function handleRegister(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const name = String(form.get("name") || "").trim();
    const email = String(form.get("email") || "").trim();
    const phone = String(form.get("phone") || "").trim();

    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const res = await inviteApi.registerWithStatus(token, { name, email, phone });
      setCandidateEmail(email);
      await attachToInterview(res);
    } catch (err) {
      if (err instanceof InviteFlowError && err.status === 409) {
        setPrefilledEmail(email);
        setDetailsMode("login");
        setInfo("Account exists — log in to continue.");
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : "Registration failed");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    const phone = String(form.get("phone") || "").trim();

    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const res = await inviteApi.login(token, { email, password, phone });
      setCandidateEmail(email);
      await attachToInterview(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleIdUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/jpg"].includes(file.type)) {
      setError("ID document must be a JPG or PNG image.");
      return;
    }
    setError(null);
    const dataUrl = await fileToDataUrl(file);
    setIdPreview(dataUrl);
    setIdDataUrl(dataUrl);
    setIdentityVerified(false);
    setVerifyMessage(null);
    setVerifyWarnings([]);
  }

  function captureSelfie() {
    const video = videoRef.current;
    if (!video) return;
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    const canvas = document.createElement("canvas");
    canvas.width = Math.min(w, 1280);
    canvas.height = Math.min(h, Math.round((canvas.width * h) / w));
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // Mirror capture to match typical front-camera preview.
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
    setSelfiePreview(dataUrl);
    setSelfieDataUrl(dataUrl);
    setSelfieSequence((current) => {
      const next = [...current];
      next[livenessStepIndex] = dataUrl;
      return next;
    });
    if (livenessStepIndex < LIVENESS_STEPS.length - 1) {
      setLivenessStepIndex((current) => current + 1);
    }
    setIdentityVerified(false);
    setVerifyMessage(null);
    setVerifyWarnings([]);
  }

  function retakeSelfie() {
    setSelfiePreview(null);
    setSelfieDataUrl(null);
    setSelfieSequence([]);
    setLivenessStepIndex(0);
    setIdentityVerified(false);
    setVerifyMessage(null);
    setVerifyWarnings([]);
  }

  async function handleVerifyIdentity() {
    if (!sessionId || !idDataUrl || !selfieDataUrl) return;
    setVerifying(true);
    setError(null);
    setVerifyMessage("Verifying your identity...");
    try {
      const res = await inviteApi.verifyIdentity(token, {
        id_image_base64: idDataUrl,
        selfie_base64: selfieDataUrl,
        selfie_frames_base64: selfieSequence,
        liveness_actions: LIVENESS_STEPS.map((step) => step.action),
        session_id: sessionId,
      });
      setVerifyMessage(null);
      setVerifyWarnings(res.data.warnings ?? []);
      if (res.data.verified) {
        setIdentityVerified(true);
        if (res.data.low_identity_confidence || res.data.message) {
          setVerifyMessage(res.data.message);
        }
      } else {
        setIdentityVerified(false);
        setVerifyMessage(res.data.message);
      }
    } catch (err) {
      setIdentityVerified(false);
      setVerifyWarnings([]);
      setVerifyMessage(
        err instanceof Error
          ? err.message
          : "Could not verify identity. Please try again.",
      );
    } finally {
      setVerifying(false);
    }
  }

  async function finishInterview() {
    if (!sessionId) return;
    let uploaded = false;
    try {
      const result = await interviewRoomRef.current?.stopAndUploadRecording();
      uploaded = result?.uploaded ?? false;
    } catch {
      uploaded = false;
    }
    const ended = await interviewApi.endInterview(sessionId);
    setRecordingSaved(uploaded);
    setSummary(ended);
    releaseInterviewMediaStream();
    setStep("summary");
  }

  async function handleChecklistReady(mediaStream: MediaStream) {
    if (!sessionId) return;
    setInterviewMediaStream(mediaStream);
    setLoading(true);
    setError(null);
    try {
      const question = await interviewApi.getCurrentQuestion(sessionId);
      setCurrentQuestion(question);
      setStep("interview");
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

  if (step === "loading") {
    return (
      <div className="invite-flow card loading">Validating your invite link…</div>
    );
  }

  if (step === "invalid") {
    return (
      <div className="invite-flow card">
        <h2>Invite unavailable</h2>
        <p className="invite-meta">
          {invalidReason || "This link has expired or is invalid"}
        </p>
      </div>
    );
  }

  return (
    <div className="invite-flow">
      {error && <div className="alert error">{error}</div>}
      {info && <div className="alert info">{info}</div>}

      {step === "welcome" && inviteInfo && (
        <div className="card invite-welcome hero-card">
          <h2>Your interview</h2>
          <p className="invite-meta">
            <strong>{inviteInfo.company}</strong> · {inviteInfo.role_title}
          </p>
          <p className="invite-meta">
            {inviteInfo.question_count} questions · {inviteInfo.difficulty}
          </p>
          <button
            type="button"
            className="primary"
            onClick={() => setStep("details")}
          >
            Continue
          </button>
        </div>
      )}

      {step === "details" && (
        <div className="card auth-panel">
          <h2>{detailsMode === "register" ? "Your details" : "Log in"}</h2>
          {detailsMode === "register" ? (
            <form onSubmit={handleRegister}>
              <label htmlFor="invite-name">Full Name</label>
              <input id="invite-name" name="name" required />
              <label htmlFor="invite-email">Email</label>
              <input
                id="invite-email"
                name="email"
                type="email"
                required
                defaultValue={prefilledEmail}
              />
              <label htmlFor="invite-phone">Phone Number</label>
              <input id="invite-phone" name="phone" type="tel" required />
              <button type="submit" className="primary" disabled={loading}>
                {loading ? "Please wait…" : "Continue"}
              </button>
            </form>
          ) : (
            <form onSubmit={handleLogin}>
              <label htmlFor="invite-login-email">Email</label>
              <input
                id="invite-login-email"
                name="email"
                type="email"
                required
                defaultValue={prefilledEmail}
                key={prefilledEmail || "login-email"}
              />
              <label htmlFor="invite-login-password">Password</label>
              <input
                id="invite-login-password"
                name="password"
                type="password"
                required
                autoComplete="current-password"
              />
              <label htmlFor="invite-login-phone">Phone Number (optional)</label>
              <input id="invite-login-phone" name="phone" type="tel" />
              <button type="submit" className="primary" disabled={loading}>
                {loading ? "Please wait…" : "Continue"}
              </button>
            </form>
          )}
          <p className="invite-meta" style={{ marginTop: "1rem" }}>
            {detailsMode === "register" ? (
              <>
                Have an account?{" "}
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setDetailsMode("login");
                    setError(null);
                    setInfo(null);
                  }}
                >
                  Log in
                </button>
              </>
            ) : (
              <>
                New here?{" "}
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setDetailsMode("register");
                    setError(null);
                    setInfo(null);
                  }}
                >
                  Register
                </button>
              </>
            )}
          </p>
        </div>
      )}

      {step === "identity" && (
        <div className="card hero-card">
          <h2>Identity check</h2>
          <div className="invite-identity-grid">
            <div className="invite-identity-panel">
              <h3>ID photo</h3>
              <p>Government ID with a clear face photo.</p>
              <input
                ref={idInputRef}
                type="file"
                accept="image/jpeg,image/png,image/jpg"
                style={{ display: "none" }}
                onChange={handleIdUpload}
              />
              <button
                type="button"
                className="secondary"
                onClick={() => idInputRef.current?.click()}
              >
                Upload ID
              </button>
              {idPreview && (
                <>
                  <img
                    className="invite-preview"
                    src={idPreview}
                    alt="ID document preview"
                    style={{ marginTop: "0.75rem" }}
                  />
                  <p className="invite-check">✓ ID uploaded</p>
                </>
              )}
            </div>

            <div className="invite-identity-panel">
              <h3>Live selfie</h3>
              <p>Complete the 4-step liveness sequence.</p>
              <div className="invite-liveness-step">
                <strong>Step {LIVENESS_STEPS[livenessStepIndex].title}</strong>
                {" — "}
                {LIVENESS_STEPS[livenessStepIndex].hint}
              </div>
              {!selfiePreview ? (
                <>
                  <video
                    ref={videoRef}
                    className="invite-selfie-video"
                    autoPlay
                    playsInline
                    muted
                  />
                  <button
                    type="button"
                    className="secondary"
                    style={{ marginTop: "0.75rem" }}
                    onClick={captureSelfie}
                  >
                    Capture
                  </button>
                </>
              ) : (
                <>
                  <img
                    className="invite-preview"
                    src={selfiePreview}
                    alt="Selfie preview"
                  />
                  <p className="invite-check">
                    ✓ {selfieSequence.filter(Boolean).length}/{LIVENESS_STEPS.length} captured
                  </p>
                  <div className="invite-liveness-progress">
                    {LIVENESS_STEPS.map((step, index) => (
                      <span
                        key={step.action}
                        className={
                          selfieSequence[index]
                            ? "invite-liveness-pill is-complete"
                            : index === livenessStepIndex
                              ? "invite-liveness-pill is-active"
                              : "invite-liveness-pill"
                        }
                      >
                        {step.title}
                      </span>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="secondary"
                    style={{ marginTop: "0.5rem" }}
                    onClick={
                      selfieSequence.filter(Boolean).length >= LIVENESS_STEPS.length
                        ? retakeSelfie
                        : captureSelfie
                    }
                  >
                    {selfieSequence.filter(Boolean).length >= LIVENESS_STEPS.length
                      ? "Restart"
                      : "Next capture"}
                  </button>
                </>
              )}
            </div>
          </div>

          <button
            type="button"
            className="primary"
            disabled={
              !idDataUrl ||
              !selfieDataUrl ||
              selfieSequence.filter(Boolean).length < LIVENESS_STEPS.length ||
              verifying
            }
            onClick={() => void handleVerifyIdentity()}
          >
            {verifying ? "Verifying…" : "Verify identity"}
          </button>

          {verifyMessage && identityVerified && (
            <div className="alert warning" style={{ marginTop: "1rem" }}>
              {verifyMessage}
            </div>
          )}

          {verifyMessage && !identityVerified && (
            <div className="alert error" style={{ marginTop: "1rem" }}>
              {verifyMessage}
            </div>
          )}

          {verifyWarnings.length > 0 && (
            <div className="alert info" style={{ marginTop: "1rem" }}>
              {verifyWarnings.map((warning) => (
                <p key={warning} style={{ marginBottom: "0.35rem" }}>
                  {warning}
                </p>
              ))}
            </div>
          )}

          {identityVerified && (
            <>
              <div className="invite-verified-banner">Verified</div>
              <button
                type="button"
                className="primary"
                onClick={() => setStep("checklist")}
              >
                Continue
              </button>
            </>
          )}
        </div>
      )}

      {step === "checklist" && sessionId && (
        <PreInterviewChecklist
          sessionId={sessionId}
          onReady={handleChecklistReady}
          loading={loading}
        />
      )}

      {step === "interview" && sessionId && currentQuestion && (
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
              candidateEmail={candidateEmail}
            />
          ) : (
            <div className="card loading">Loading next question…</div>
          )}
        </>
      )}

      {step === "summary" && summary && sessionId && (
        <Summary
          summary={summary}
          sessionId={sessionId}
          inviteToken={token}
          candidateEmail={candidateEmail}
          recordingSaved={recordingSaved}
          onRestart={() => window.location.reload()}
        />
      )}
    </div>
  );
}
