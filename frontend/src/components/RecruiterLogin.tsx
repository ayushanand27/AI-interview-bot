import { useState } from "react";
import { authApi, setAccessToken, setRefreshToken } from "../api/client";
import "../recruiter-portal.css";
import PasswordInput from "./PasswordInput";

type Mode = "login" | "register";

export default function RecruiterLogin() {
  const [mode, setMode] = useState<Mode>("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotMessage, setForgotMessage] = useState<string | null>(null);
  const [forgotResetUrl, setForgotResetUrl] = useState<string | null>(null);
  const [postRegisterNote, setPostRegisterNote] = useState<string | null>(null);
  const [postRegisterLink, setPostRegisterLink] = useState<string | null>(null);

  async function handleLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");

    setLoading(true);
    setError(null);
    try {
      const res = await authApi.login(email, password);
      setAccessToken(res.data.access_token);
      setRefreshToken(res.data.refresh_token);
      const me = await authApi.me();
      if (me.data.role !== "recruiter") {
        setAccessToken(null);
        setRefreshToken(null);
        setError("This portal is for recruiters only. Please use a recruiter account.");
        return;
      }
      window.location.href = "/recruiter/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const companyName = String(form.get("company_name") || "").trim();
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    const phone = String(form.get("phone") || "").trim();

    const fullName = phone ? `${companyName} (${phone})` : companyName;

    setLoading(true);
    setError(null);
    setPostRegisterNote(null);
    setPostRegisterLink(null);
    try {
      const res = await authApi.register(fullName, email, password, "recruiter");
      setAccessToken(res.data.access_token);
      setRefreshToken(res.data.refresh_token);
      if (res.data.email_note) {
        setPostRegisterNote(
          res.data.email_note ||
            res.message ||
            "Account created, but we could not send the verification email.",
        );
        setPostRegisterLink(res.data.verification_url ?? null);
        return;
      }
      window.location.href = "/recruiter/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleForgotPassword(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const email = forgotEmail.trim();
    if (!email) return;

    setLoading(true);
    setError(null);
    setForgotMessage(null);
    setForgotResetUrl(null);
    try {
      const result = await authApi.forgotPassword(email);
      if (result.reset_url) {
        setForgotMessage(
          result.email_note
            ? `Email delivery failed (${result.email_note}). Use this reset link:`
            : result.message ||
                "If this email exists, use this reset link (local/dev):",
        );
        setForgotResetUrl(result.reset_url);
      } else {
        setForgotMessage(
          result.message ||
            "If this email exists, check your inbox (and spam folder).",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="recruiter-portal">
      <header>
        <h1>AI Interview Bot</h1>
        <p>Recruiter sign-in</p>
      </header>

      <div className="rp-card status-panel">
        {!showForgotPassword && (
          <div className="rp-tabs">
            <button
              type="button"
              className={mode === "login" ? "active" : undefined}
              onClick={() => {
                setMode("login");
                setError(null);
                setShowForgotPassword(false);
                setForgotMessage(null);
                setForgotResetUrl(null);
              }}
            >
              Login
            </button>
            <button
              type="button"
              className={mode === "register" ? "active" : undefined}
              onClick={() => {
                setMode("register");
                setError(null);
                setShowForgotPassword(false);
                setForgotMessage(null);
                setForgotResetUrl(null);
              }}
            >
              Register
            </button>
          </div>
        )}

        {error && <div className="rp-alert error">{error}</div>}

        {postRegisterNote ? (
          <div className="stack">
            <div className="rp-alert info">{postRegisterNote}</div>
            {postRegisterLink && (
              <p style={{ wordBreak: "break-all", fontSize: "0.9rem" }}>
                Verification link:{" "}
                <a href={postRegisterLink}>{postRegisterLink}</a>
              </p>
            )}
            <button
              type="button"
              className="rp-primary"
              onClick={() => {
                window.location.href = "/recruiter/dashboard";
              }}
            >
              Continue to dashboard
            </button>
          </div>
        ) : showForgotPassword ? (
          <form onSubmit={handleForgotPassword}>
            <h2 className="rp-section-title" style={{ marginTop: 0 }}>
              Reset password
            </h2>
            <label htmlFor="recruiter-forgot-email">Email</label>
            <input
              id="recruiter-forgot-email"
              type="email"
              required
              autoComplete="email"
              value={forgotEmail}
              onChange={(e) => setForgotEmail(e.target.value)}
              disabled={loading}
            />
            {forgotMessage && (
              <div className="rp-alert info" style={{ marginTop: "0.75rem" }}>
                <p>{forgotMessage}</p>
                {forgotResetUrl && (
                  <p style={{ marginTop: "0.5rem", wordBreak: "break-all" }}>
                    <a href={forgotResetUrl}>{forgotResetUrl}</a>
                  </p>
                )}
              </div>
            )}
            <div className="rp-actions" style={{ marginTop: "0.75rem" }}>
              <button type="submit" className="rp-primary" disabled={loading}>
                {loading ? "Sending…" : "Send reset link"}
              </button>
              <button
                type="button"
                className="rp-secondary"
                disabled={loading}
                onClick={() => {
                  setShowForgotPassword(false);
                  setForgotMessage(null);
                  setForgotResetUrl(null);
                  setError(null);
                }}
              >
                Back to login
              </button>
            </div>
          </form>
        ) : mode === "login" ? (
          <form onSubmit={handleLogin}>
            <label htmlFor="recruiter-login-email">Email</label>
            <input
              id="recruiter-login-email"
              name="email"
              type="email"
              required
              autoComplete="email"
            />
            <label htmlFor="recruiter-login-password">Password</label>
            <PasswordInput
              id="recruiter-login-password"
              name="password"
              required
              autoComplete="current-password"
            />
            <button
              type="button"
              className="link-button"
              style={{ margin: "0.35rem 0 0.75rem", fontSize: "0.85rem" }}
              onClick={() => {
                setShowForgotPassword(true);
                setError(null);
              }}
              disabled={loading}
            >
              Forgot password?
            </button>
            <button type="submit" className="rp-primary" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister}>
            <label htmlFor="recruiter-company">Company</label>
            <input id="recruiter-company" name="company_name" required />
            <label htmlFor="recruiter-register-email">Email</label>
            <input
              id="recruiter-register-email"
              name="email"
              type="email"
              required
              autoComplete="email"
            />
            <label htmlFor="recruiter-register-password">Password</label>
            <PasswordInput
              id="recruiter-register-password"
              name="password"
              required
              minLength={8}
              autoComplete="new-password"
            />
            <label htmlFor="recruiter-phone">Phone (optional)</label>
            <input id="recruiter-phone" name="phone" type="tel" />
            <button type="submit" className="rp-primary" disabled={loading}>
              {loading ? "Creating…" : "Create account"}
            </button>
          </form>
        )}
      </div>
      <p className="rp-footer">
        <a href="/">Candidate login</a>
        {" · "}
        <a href="/privacy">Privacy Policy</a>
      </p>
    </div>
  );
}
