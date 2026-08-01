import { useState } from "react";
import { authApi } from "../api/client";
import PasswordInput from "./PasswordInput";

export default function ResetPassword() {
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!token) {
      setError("Invalid or expired reset link");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    setLoading(true);
    try {
        const result = await authApi.resetPassword(token, password);
      const message =
        result?.message ??
        (result as { data?: { message?: string } })?.data?.message ??
        "Password reset successfully. You can now login with your new password.";
      sessionStorage.setItem("ss_password_reset_done", "1");
      setSuccess(message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Reset Password</h1>
        <p>Set a new password to regain access to your interview account.</p>
      </header>

      <div className="card auth-panel stack" style={{ maxWidth: "480px", margin: "0 auto" }}>
        {success ? (
          <>
            <div className="alert success">Password reset! You can now login.</div>
            <p>{success}</p>
            <button
              type="button"
              className="primary"
              onClick={() => {
                window.location.href = "/";
              }}
            >
              Login
            </button>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            {!token && (
              <div className="alert error" style={{ marginBottom: "1rem" }}>
                Invalid or expired reset link
              </div>
            )}

            <div className="field">
              <label htmlFor="new_password">New Password</label>
              <PasswordInput
                id="new_password"
                name="new_password"
                minLength={8}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading || !token}
              />
            </div>

            <div className="field">
              <label htmlFor="confirm_password">Confirm Password</label>
              <PasswordInput
                id="confirm_password"
                name="confirm_password"
                minLength={8}
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={loading || !token}
              />
            </div>

            {error && <div className="alert error">{error}</div>}

            <button type="submit" className="primary" disabled={loading || !token}>
              {loading ? "Resetting…" : "Reset password"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
