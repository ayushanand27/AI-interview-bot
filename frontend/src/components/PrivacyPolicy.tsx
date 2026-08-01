import { useEffect, useState } from "react";
import {
  authApi,
  getAccessToken,
  loadStoredRefreshToken,
  privacyApi,
  setAccessToken,
  setRefreshToken,
} from "../api/client";
import type { UserResponse } from "../types/auth";
import "../recruiter-portal.css";

type StatusMsg = { kind: "ok" | "err" | "info"; text: string } | null;

export default function PrivacyPolicy() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<StatusMsg>(null);

  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleteFiles, setDeleteFiles] = useState(true);

  const [adminEmail, setAdminEmail] = useState("");
  const [adminConfirm, setAdminConfirm] = useState(false);
  const [adminDeleteFiles, setAdminDeleteFiles] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      loadStoredRefreshToken();
      const refresh = loadStoredRefreshToken();
      try {
        if (!getAccessToken() && refresh) {
          const tokens = await authApi.refresh(refresh);
          setAccessToken(tokens.data.access_token);
          setRefreshToken(tokens.data.refresh_token);
        }
        if (getAccessToken() || refresh) {
          const me = await authApi.me();
          if (!cancelled) setUser(me.data);
        }
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setAuthChecked(true);
      }
    }

    void boot();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleExport(format: "json" | "zip") {
    setBusy(true);
    setStatus(null);
    try {
      if (format === "zip") {
        const blob = await privacyApi.exportMyDataZip();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "dsar_export.zip";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        setStatus({ kind: "ok", text: "Export downloaded (ZIP)." });
      } else {
        const data = await privacyApi.exportMyDataJson();
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "dsar_export.json";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        setStatus({ kind: "ok", text: "Export downloaded (JSON)." });
      }
    } catch (err) {
      setStatus({
        kind: "err",
        text: err instanceof Error ? err.message : "Export failed",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!deleteConfirm) {
      setStatus({
        kind: "err",
        text: "Check the confirmation box to anonymize your data.",
      });
      return;
    }
    if (
      !window.confirm(
        "This anonymizes your account and related interview artifacts. Continue?",
      )
    ) {
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      const res = await privacyApi.deleteMyData({
        confirm: true,
        delete_files: deleteFiles,
      });
      setStatus({
        kind: "ok",
        text:
          typeof res.message === "string"
            ? res.message
            : "Delete/anonymize request completed.",
      });
    } catch (err) {
      setStatus({
        kind: "err",
        text: err instanceof Error ? err.message : "Delete request failed",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleAdminExport(format: "json" | "zip") {
    const email = adminEmail.trim().toLowerCase();
    if (!email || !email.includes("@")) {
      setStatus({ kind: "err", text: "Enter a valid candidate email." });
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      if (format === "zip") {
        const blob = await privacyApi.adminExportZip(email);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `dsar_${email}.zip`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        setStatus({ kind: "ok", text: `Exported ZIP for ${email}.` });
      } else {
        const data = await privacyApi.adminExportJson(email);
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `dsar_${email}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        setStatus({ kind: "ok", text: `Exported JSON for ${email}.` });
      }
    } catch (err) {
      setStatus({
        kind: "err",
        text: err instanceof Error ? err.message : "Admin export failed",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleAdminDelete() {
    const email = adminEmail.trim().toLowerCase();
    if (!email || !email.includes("@")) {
      setStatus({ kind: "err", text: "Enter a valid candidate email." });
      return;
    }
    if (!adminConfirm) {
      setStatus({
        kind: "err",
        text: "Check confirmation to anonymize candidate data.",
      });
      return;
    }
    if (
      !window.confirm(
        `Anonymize invite-linked data for ${email}? This cannot be undone.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      const res = await privacyApi.adminDelete(email, {
        confirm: true,
        delete_files: adminDeleteFiles,
      });
      setStatus({
        kind: "ok",
        text:
          typeof res.message === "string"
            ? res.message
            : `Anonymized data for ${email}.`,
      });
    } catch (err) {
      setStatus({
        kind: "err",
        text: err instanceof Error ? err.message : "Admin delete failed",
      });
    } finally {
      setBusy(false);
    }
  }

  const isRecruiter = user?.role === "recruiter";

  return (
    <div className="recruiter-portal">
      <header>
        <h1>Privacy</h1>
        <p>Policy and data subject requests (DSAR)</p>
      </header>

      <div className="rp-card rp-card-wide rp-card-spacing">
        <section className="privacy-section">
          <h2>Overview</h2>
          <p>
            AI Interview Bot helps recruiters run AI-assisted technical interviews and
            review candidate performance. This page describes what data we collect and
            lets signed-in users exercise export / delete rights.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Data we collect</h2>
          <ul>
            <li>
              <strong>Account data:</strong> name, email, password (hashed), and
              role (candidate or recruiter).
            </li>
            <li>
              <strong>Interview content:</strong> job descriptions, resume text,
              spoken answers (transcribed), AI-generated questions, and scoring
              feedback.
            </li>
            <li>
              <strong>Proctoring data:</strong> webcam snapshots during the
              interview, identity verification images (ID and selfie when
              provided), and integrity signals such as tab switches or face
              detection events.
            </li>
            <li>
              <strong>Recordings:</strong> optional session recordings when
              enabled by the recruiter.
            </li>
          </ul>
        </section>

        <section className="privacy-section">
          <h2>How we use data</h2>
          <ul>
            <li>Conduct and score interviews using AI models (Groq).</li>
            <li>Generate reports for recruiters and optional candidate summaries.</li>
            <li>Detect proctoring violations and flag sessions for human review.</li>
            <li>Authenticate users and secure the platform.</li>
          </ul>
        </section>

        <section className="privacy-section">
          <h2>Storage &amp; retention</h2>
          <p>
            Data is stored on servers controlled by the platform operator.
            Interview sessions and reports are retained so recruiters can review
            completed interviews. You may request deletion below when signed in.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Third parties</h2>
          <p>
            We use Groq for question generation, transcription, and answer
            judging. Email delivery may use SMTP providers configured by the
            operator. Coding tests may run on SandboxAPI (RapidAPI) or Piston.
            We do not sell personal data.
          </p>
        </section>

        <section className="privacy-section" id="dsar">
          <h2>Your data rights (DSAR)</h2>
          {!authChecked ? (
            <p className="rp-muted-small">Checking sign-in…</p>
          ) : !user ? (
            <p>
              <a href="/">Sign in</a> to export or anonymize your own data. Recruiters
              can also process invite-linked candidate emails below after logging into
              the <a href="/recruiter">recruiter portal</a>.
            </p>
          ) : (
            <>
              <p className="rp-muted-small" style={{ marginBottom: "0.75rem" }}>
                Signed in as <strong>{user.email}</strong> ({user.role}).
              </p>
              <div className="rp-actions" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                <button
                  type="button"
                  className="rp-secondary"
                  disabled={busy}
                  onClick={() => void handleExport("json")}
                >
                  Export my data (JSON)
                </button>
                <button
                  type="button"
                  className="rp-secondary"
                  disabled={busy}
                  onClick={() => void handleExport("zip")}
                >
                  Export my data (ZIP)
                </button>
              </div>
              <div style={{ marginTop: "1rem" }}>
                <label className="rp-muted-small" style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="checkbox"
                    checked={deleteConfirm}
                    onChange={(e) => setDeleteConfirm(e.target.checked)}
                    disabled={busy}
                  />
                  I understand anonymization is irreversible
                </label>
                <label
                  className="rp-muted-small"
                  style={{ display: "flex", gap: "0.5rem", marginTop: "0.35rem" }}
                >
                  <input
                    type="checkbox"
                    checked={deleteFiles}
                    onChange={(e) => setDeleteFiles(e.target.checked)}
                    disabled={busy}
                  />
                  Also delete identity images and recordings from storage
                </label>
                <button
                  type="button"
                  className="rp-danger"
                  style={{ marginTop: "0.75rem" }}
                  disabled={busy}
                  onClick={() => void handleDelete()}
                >
                  Request delete / anonymize
                </button>
              </div>
            </>
          )}
        </section>

        {authChecked && isRecruiter && (
          <section className="privacy-section" id="dsar-recruiter">
            <h2>Recruiter DSAR (by candidate email)</h2>
            <p className="rp-muted-small">
              Export or anonymize invite-linked candidate verification data for emails
              on your assessments.
            </p>
            <label className="rp-muted-small" style={{ display: "block" }}>
              Candidate email
              <input
                type="email"
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                placeholder="candidate@example.com"
                disabled={busy}
                style={{ display: "block", width: "100%", marginTop: "0.35rem" }}
              />
            </label>
            <div
              className="rp-actions"
              style={{ marginTop: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}
            >
              <button
                type="button"
                className="rp-secondary"
                disabled={busy}
                onClick={() => void handleAdminExport("json")}
              >
                Export JSON
              </button>
              <button
                type="button"
                className="rp-secondary"
                disabled={busy}
                onClick={() => void handleAdminExport("zip")}
              >
                Export ZIP
              </button>
            </div>
            <label
              className="rp-muted-small"
              style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}
            >
              <input
                type="checkbox"
                checked={adminConfirm}
                onChange={(e) => setAdminConfirm(e.target.checked)}
                disabled={busy}
              />
              Confirm irreversible anonymization
            </label>
            <label
              className="rp-muted-small"
              style={{ display: "flex", gap: "0.5rem", marginTop: "0.35rem" }}
            >
              <input
                type="checkbox"
                checked={adminDeleteFiles}
                onChange={(e) => setAdminDeleteFiles(e.target.checked)}
                disabled={busy}
              />
              Also delete stored files
            </label>
            <button
              type="button"
              className="rp-danger"
              style={{ marginTop: "0.75rem" }}
              disabled={busy}
              onClick={() => void handleAdminDelete()}
            >
              Anonymize by email
            </button>
          </section>
        )}

        {status && (
          <div
            className={
              status.kind === "ok"
                ? "alert success"
                : status.kind === "err"
                  ? "alert error"
                  : "alert info"
            }
            style={{ marginTop: "1rem" }}
          >
            {status.text}
          </div>
        )}

        <p className="rp-muted-small">
          <a href="/">← Back to home</a>
          {" · "}
          <a href="/recruiter">Recruiter login</a>
        </p>
      </div>
    </div>
  );
}
