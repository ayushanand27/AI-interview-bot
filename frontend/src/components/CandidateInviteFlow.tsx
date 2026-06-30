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
  const [verifying, setVerifying] = useState(false);
  const [identityVerified, setIdentityVerified] = useState(false);
  const [verifyMessage, setVerifyMessage] = useState<string | null>(null);

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
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user" }, audio: false })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        selfieStreamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      })
      .catch((err) => {
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
      });

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
        setInfo("You already have an account. Log in below to continue this interview.");
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
    setIdentityVerified(false);
    setVerifyMessage(null);
  }

  function retakeSelfie() {
    setSelfiePreview(null);
    setSelfieDataUrl(null);
    setIdentityVerified(false);
    setVerifyMessage(null);
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
        session_id: sessionId,
      });
      setVerifyMessage(null);
      if (res.data.verified) {
        setIdentityVerified(true);
        if (res.data.low_identity_confidence) {
          setVerifyMessage(res.data.message);
        }
      } else {
        setIdentityVerified(false);
        setVerifyMessage(res.data.message);
      }
    } catch (err) {
      setIdentityVerified(false);
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
          <h2>Welcome to your interview</h2>
          <p className="invite-meta">
            <strong>{inviteInfo.company}</strong> has invited you to interview for{" "}
            <strong>{inviteInfo.role_title}</strong>.
          </p>
          <p className="invite-meta">
            {inviteInfo.question_count} questions · {inviteInfo.difficulty} difficulty
          </p>
          <button
            type="button"
            className="primary"
            onClick={() => setStep("details")}
          >
            Start Your Interview
          </button>
        </div>
      )}

      {step === "details" && (
        <div className="card auth-panel">
          <h2>{detailsMode === "register" ? "Your details" : "Log in to continue"}</h2>
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
                {loading ? "Please wait…" : "Log in and continue"}
              </button>
            </form>
          )}
          <p className="invite-meta" style={{ marginTop: "1rem" }}>
            {detailsMode === "register" ? (
              <>
                Already have an account?{" "}
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
                New candidate?{" "}
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setDetailsMode("register");
                    setError(null);
                    setInfo(null);
                  }}
                >
                  Register instead
                </button>
              </>
            )}
          </p>
        </div>
      )}

      {step === "identity" && (
        <div className="card hero-card">
          <h2>Identity Verification</h2>
          <div className="invite-identity-grid">
            <div className="invite-identity-panel">
              <h3>ID Document</h3>
              <p>
                Upload a clear photo of your government ID (Aadhaar, PAN, Passport, or
                Driving License). Your face must be visible and not too small in the image.
              </p>
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
                Upload ID photo
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
              <h3>Live Selfie</h3>
              <p>Take a selfie in good lighting, facing the camera directly.</p>
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
                    Capture Photo
                  </button>
                </>
              ) : (
                <>
                  <img
                    className="invite-preview"
                    src={selfiePreview}
                    alt="Selfie preview"
                  />
                  <p className="invite-check">✓ Selfie captured</p>
                  <button
                    type="button"
                    className="secondary"
                    style={{ marginTop: "0.5rem" }}
                    onClick={retakeSelfie}
                  >
                    Retake
                  </button>
                </>
              )}
            </div>
          </div>

          <button
            type="button"
            className="primary"
            disabled={!idDataUrl || !selfieDataUrl || verifying}
            onClick={() => void handleVerifyIdentity()}
          >
            {verifying ? "Verifying your identity…" : "Verify My Identity"}
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

          {identityVerified && (
            <>
              <div className="invite-verified-banner">Identity Verified</div>
              <button
                type="button"
                className="primary"
                onClick={() => setStep("checklist")}
              >
                Proceed to Interview
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
              onEndEarly={handleEndEarly}
              onIdleTimeout={handleIdleTimeout}
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
