import { useEffect, useState } from "react";
import { authApi } from "../api/client";

type Status = "loading" | "success" | "error";

export default function VerifyEmail() {
  const [status, setStatus] = useState<Status>("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token")?.trim();

    if (!token) {
      setStatus("error");
      setMessage("Invalid verification link - no token found");
      return;
    }

    let cancelled = false;

    async function verify(verificationToken: string) {
      try {
        const result = await authApi.verifyEmail(verificationToken);

        if (cancelled) return;

        if (result.success) {
          sessionStorage.setItem("ss_dismiss_register_verify", "1");
          sessionStorage.removeItem("ss_register_verify_notice");
          setStatus("success");
          setMessage(result.message || "Email verified successfully!");
          window.setTimeout(() => {
            window.location.href = "/";
          }, 2000);
          return;
        }

        setStatus("error");
        setMessage(result.message || "Invalid or expired verification link");
      } catch (err) {
        if (!cancelled) {
          setStatus("error");
          setMessage(
            err instanceof Error
              ? err.message
              : "Something went wrong. Please try again.",
          );
        }
      }
    }

    void verify(token);
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") {
    return (
      <div className="app">
        <div className="card status-panel" style={{ textAlign: "center", padding: "40px", maxWidth: "560px", margin: "0 auto" }}>
          <p>Verifying your email...</p>
        </div>
      </div>
    );
  }

  if (status === "success") {
    return (
      <div className="app">
        <div className="card status-panel" style={{ textAlign: "center", padding: "40px", maxWidth: "560px", margin: "0 auto" }}>
          <h2 style={{ color: "#86efac" }}>Email Verified!</h2>
          <p>{message || "Your email has been verified successfully."}</p>
          <p className="invite-meta" style={{ marginTop: "0.75rem" }}>
            Redirecting you to the app…
          </p>
          <button
            type="button"
            onClick={() => {
              window.location.href = "/";
            }}
            className="primary"
            style={{ marginTop: "16px" }}
          >
            Continue to app
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="card status-panel" style={{ textAlign: "center", padding: "40px", maxWidth: "560px", margin: "0 auto" }}>
        <h2 style={{ color: "#fca5a5" }}>Verification Failed</h2>
        <p>{message}</p>
        <button
          type="button"
          onClick={() => {
            window.location.href = "/";
          }}
          className="primary"
          style={{ marginTop: "16px" }}
        >
          Back to Login
        </button>
      </div>
    </div>
  );
}
