import { useState } from "react";
import { authApi, setAccessToken, setRefreshToken } from "../api/client";
import type { UserResponse } from "../types/auth";

type AuthMode = "login" | "register";

export interface AuthSuccess {
  accessToken: string;
  refreshToken: string;
  user: UserResponse;
  justRegistered?: boolean;
}

interface AuthProps {
  loading: boolean;
  onLoadingChange: (loading: boolean) => void;
  onError: (message: string | null) => void;
  onAuthenticated: (payload: AuthSuccess) => void;
}

export default function Auth({
  loading,
  onLoadingChange,
  onError,
  onAuthenticated,
}: AuthProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotMessage, setForgotMessage] = useState<string | null>(null);
  async function handleLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");

    onLoadingChange(true);
    onError(null);
    try {
      const res = await authApi.login(email, password);
      setAccessToken(res.data.access_token);
      setRefreshToken(res.data.refresh_token);
      const me = await authApi.me();
      onAuthenticated({
        accessToken: res.data.access_token,
        refreshToken: res.data.refresh_token,
        user: me.data,
      });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Login failed");
    } finally {
      onLoadingChange(false);
    }
  }

  async function handleRegister(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const full_name = String(form.get("full_name") || "").trim();
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    const role = String(form.get("role") || "candidate") as
      | "candidate"
      | "recruiter";

    onLoadingChange(true);
    onError(null);
    try {
      const res = await authApi.register(full_name, email, password, role);
      setAccessToken(res.data.access_token);
      setRefreshToken(res.data.refresh_token);
      onAuthenticated({
        accessToken: res.data.access_token,
        refreshToken: res.data.refresh_token,
        user: res.data.user,
        justRegistered: true,
      });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      onLoadingChange(false);
    }
  }

  async function handleForgotPassword(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const email = forgotEmail.trim();
    if (!email) return;

    onLoadingChange(true);
    onError(null);
    setForgotMessage(null);
    try {
      await authApi.forgotPassword(email);
      setForgotMessage("If this email exists, check your inbox.");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Request failed");
    } finally {
      onLoadingChange(false);
    }
  }

  return (
    <div className="card auth-panel stack">
      <div className="auth-toggle" style={{ marginBottom: "1.25rem" }}>
        <button
          type="button"
          className={mode === "login" ? "primary" : "secondary"}
          onClick={() => {
            setMode("login");
            onError(null);
            setShowForgotPassword(false);
            setForgotMessage(null);
          }}
          disabled={loading}
        >
          Log in
        </button>
        <button
          type="button"
          className={mode === "register" ? "primary" : "secondary"}
          onClick={() => {
            setMode("register");
            onError(null);
            setShowForgotPassword(false);
            setForgotMessage(null);
          }}
          disabled={loading}
          style={{ marginLeft: "0.5rem" }}
        >
          Register
        </button>
      </div>

      {mode === "login" ? (
        showForgotPassword ? (
          <form onSubmit={handleForgotPassword}>
            <h2 className="section-title">Reset your password</h2>

            <div className="field">
              <label htmlFor="forgot_email">Email</label>
              <input
                id="forgot_email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={forgotEmail}
                onChange={(e) => setForgotEmail(e.target.value)}
                disabled={loading}
              />
            </div>

            {forgotMessage && (
              <div className="alert info">{forgotMessage}</div>
            )}

            <button type="submit" className="primary" disabled={loading}>
              {loading ? "Sending…" : "Send reset link"}
            </button>

            <button
              type="button"
              className="secondary"
              style={{ marginLeft: "0.5rem" }}
              onClick={() => {
                setShowForgotPassword(false);
                setForgotMessage(null);
                onError(null);
              }}
              disabled={loading}
            >
              Back to login
            </button>
          </form>
        ) : (
          <form onSubmit={handleLogin}>
            <h2 className="section-title">Log in to your account</h2>

            <div className="field">
              <label htmlFor="login_email">Email</label>
              <input
                id="login_email"
                name="email"
                type="email"
                autoComplete="email"
                required
                disabled={loading}
              />
            </div>

            <div className="field">
              <label htmlFor="login_password">Password</label>
              <input
                id="login_password"
                name="password"
                type="password"
                autoComplete="current-password"
                minLength={8}
                required
                disabled={loading}
              />
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setShowForgotPassword(true);
                  onError(null);
                }}
                disabled={loading}
                style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}
              >
                Forgot password?
              </button>
            </div>

            <button type="submit" className="primary" disabled={loading}>
              {loading ? "Logging in…" : "Log in"}
            </button>
          </form>
        )
      ) : (
        <form onSubmit={handleRegister}>
          <h2 className="section-title">Create an account</h2>

          <div className="field">
            <label htmlFor="register_full_name">Full name</label>
            <input
              id="register_full_name"
              name="full_name"
              type="text"
              autoComplete="name"
              required
              disabled={loading}
            />
          </div>

          <div className="field">
            <label htmlFor="register_email">Email</label>
            <input
              id="register_email"
              name="email"
              type="email"
              autoComplete="email"
              required
              disabled={loading}
            />
          </div>

          <div className="field">
            <label htmlFor="register_password">Password</label>
            <input
              id="register_password"
              name="password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              required
              disabled={loading}
            />
          </div>

          <div className="field">
            <label htmlFor="register_role">Role</label>
            <select
              id="register_role"
              name="role"
              defaultValue="candidate"
              disabled={loading}
            >
              <option value="candidate">Candidate</option>
              <option value="recruiter">Recruiter</option>
            </select>
          </div>

          <button type="submit" className="primary" disabled={loading}>
            {loading ? "Creating account…" : "Register"}
          </button>
        </form>
      )}
      <p className="auth-footer">
        <a href="/privacy">Privacy Policy</a>
      </p>
    </div>
  );
}
