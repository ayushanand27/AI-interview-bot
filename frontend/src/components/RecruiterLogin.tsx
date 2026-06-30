import { useState } from "react";
import { authApi, setAccessToken, setRefreshToken } from "../api/client";
import "../recruiter-portal.css";

type Mode = "login" | "register";

export default function RecruiterLogin() {
  const [mode, setMode] = useState<Mode>("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    try {
      const res = await authApi.register(fullName, email, password, "recruiter");
      setAccessToken(res.data.access_token);
      setRefreshToken(res.data.refresh_token);
      window.location.href = "/recruiter/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="recruiter-portal">
      <header>
        <h1>AI Interview Bot — Recruiter Portal</h1>
        <p>Sign in to create assessments and review completed interviews.</p>
      </header>

      <div className="rp-card status-panel">
        <div className="rp-tabs">
          <button
            type="button"
            className={mode === "login" ? "active" : undefined}
            onClick={() => {
              setMode("login");
              setError(null);
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
            }}
          >
            Register
          </button>
        </div>

        {error && <div className="rp-alert error">{error}</div>}

        {mode === "login" ? (
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
            <input
              id="recruiter-login-password"
              name="password"
              type="password"
              required
              autoComplete="current-password"
            />
            <button type="submit" className="rp-primary" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister}>
            <label htmlFor="recruiter-company">Company Name</label>
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
            <input
              id="recruiter-register-password"
              name="password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
            />
            <label htmlFor="recruiter-phone">Phone</label>
            <input id="recruiter-phone" name="phone" type="tel" />
            <button type="submit" className="rp-primary" disabled={loading}>
              {loading ? "Creating account…" : "Create recruiter account"}
            </button>
          </form>
        )}
      </div>
      <p className="rp-footer">
        <a href="/privacy">Privacy Policy</a>
      </p>
    </div>
  );
}
