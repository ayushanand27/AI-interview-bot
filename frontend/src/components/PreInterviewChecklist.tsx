import { useEffect, useRef, useState } from "react";
import { proctorApi } from "../api/client";
import {
  extensionBlockMessage,
  scanInterviewEnvironment,
  type DetectedExtension,
  type VirtualCameraResult,
} from "../hooks/useExtensionDetection";

interface PreInterviewChecklistProps {
  sessionId: string;
  onReady: (mediaStream: MediaStream) => void;
  loading?: boolean;
}

function getFullscreenElement(): Element | null {
  const doc = document as Document & {
    webkitFullscreenElement?: Element | null;
  };
  return doc.fullscreenElement ?? doc.webkitFullscreenElement ?? null;
}

async function requestDocumentFullscreen(): Promise<void> {
  const el = document.documentElement as HTMLElement & {
    webkitRequestFullscreen?: () => Promise<void> | void;
  };
  if (el.requestFullscreen) {
    await el.requestFullscreen();
    return;
  }
  if (el.webkitRequestFullscreen) {
    await el.webkitRequestFullscreen();
  }
}

export default function PreInterviewChecklist({
  sessionId,
  onReady,
  loading = false,
}: PreInterviewChecklistProps) {
  const [cameraGranted, setCameraGranted] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [requestingCamera, setRequestingCamera] = useState(false);

  const [detectedExtensions, setDetectedExtensions] = useState<DetectedExtension[]>([]);
  const [automaticScan, setAutomaticScan] = useState(false);
  const [virtualCamera, setVirtualCamera] = useState<VirtualCameraResult>({
    detected: false,
    confidence: "none",
    blockRecommended: false,
    warnOnly: false,
    deviceLabels: [],
    message: null,
  });
  const [screenSharingActive, setScreenSharingActive] = useState(false);
  const [screenSharingCapability, setScreenSharingCapability] = useState(false);
  const [checking, setChecking] = useState(false);

  const [closedTabs, setClosedTabs] = useState(false);
  const [disabledExtensions, setDisabledExtensions] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const [envVerifying, setEnvVerifying] = useState(false);
  const [envAllowed, setEnvAllowed] = useState<boolean | null>(null);
  const [envBlockReason, setEnvBlockReason] = useState<string | null>(null);
  const [envWarnings, setEnvWarnings] = useState<string[]>([]);

  const mediaStreamRef = useRef<MediaStream | null>(null);
  const streamTransferredRef = useRef(false);

  async function runEnvironmentScan() {
    setChecking(true);
    try {
      const result = await scanInterviewEnvironment(mediaStreamRef.current);
      setDetectedExtensions(result.extensions.detected);
      setAutomaticScan(result.extensions.scanSupported);
      setVirtualCamera(result.virtualCamera);
      setScreenSharingActive(result.screenSharingActive);
      setScreenSharingCapability(result.screenSharingCapability);
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    if (!cameraGranted) return;
    void runEnvironmentScan();
  }, [cameraGranted]);

  useEffect(() => {
    function syncFullscreen() {
      setIsFullscreen(Boolean(getFullscreenElement()));
    }
    syncFullscreen();
    document.addEventListener("fullscreenchange", syncFullscreen);
    document.addEventListener("webkitfullscreenchange", syncFullscreen);
    return () => {
      document.removeEventListener("fullscreenchange", syncFullscreen);
      document.removeEventListener("webkitfullscreenchange", syncFullscreen);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (!streamTransferredRef.current) {
        mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
      }
      mediaStreamRef.current = null;
    };
  }, []);

  const hasExtensions = detectedExtensions.length > 0;
  const localChecksPass =
    cameraGranted &&
    closedTabs &&
    disabledExtensions &&
    isFullscreen &&
    !hasExtensions &&
    !virtualCamera.blockRecommended &&
    !screenSharingActive;

  useEffect(() => {
    if (!localChecksPass || checking) {
      setEnvAllowed(null);
      setEnvBlockReason(null);
      setEnvWarnings([]);
      return;
    }

    let cancelled = false;
    setEnvVerifying(true);
    setEnvBlockReason(null);

    proctorApi
      .verifyEnvironment({
        session_id: sessionId,
        user_agent: navigator.userAgent,
        detected_extensions: detectedExtensions.map((e) => ({
          id: e.id,
          name: e.name,
        })),
        virtual_camera_detected: virtualCamera.blockRecommended,
        virtual_camera_uncertain: virtualCamera.warnOnly,
        screen_sharing_active: screenSharingActive,
        screen_sharing_capability:
          screenSharingCapability && !screenSharingActive,
      })
      .then((res) => {
        if (cancelled) return;
        setEnvAllowed(res.allowed);
        setEnvBlockReason(res.allowed ? null : res.reason ?? "Environment check failed");
        setEnvWarnings(res.warnings ?? []);
      })
      .catch(() => {
        if (cancelled) return;
        setEnvAllowed(false);
        setEnvBlockReason(
          "Could not verify interview environment. Check your connection and try again.",
        );
      })
      .finally(() => {
        if (!cancelled) setEnvVerifying(false);
      });

    return () => {
      cancelled = true;
    };
  }, [
    localChecksPass,
    checking,
    sessionId,
    detectedExtensions,
    virtualCamera.blockRecommended,
    virtualCamera.warnOnly,
    screenSharingActive,
    screenSharingCapability,
  ]);

  async function grantCameraAccess() {
    setRequestingCamera(true);
    setCameraError(null);
    try {
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true,
      });
      mediaStreamRef.current = stream;
      setCameraGranted(true);
    } catch {
      setCameraGranted(false);
      setCameraError("Camera and microphone access are required for the interview");
    } finally {
      setRequestingCamera(false);
    }
  }

  async function enterFullscreen() {
    try {
      await requestDocumentFullscreen();
    } catch {
      // User denied or browser blocked — isFullscreen stays false
    }
  }

  function handleReady() {
    const stream = mediaStreamRef.current;
    if (!stream) return;
    streamTransferredRef.current = true;
    mediaStreamRef.current = null;
    onReady(stream);
  }

  const canProceed =
    localChecksPass && envAllowed === true && !envVerifying && !loading;

  return (
    <div className="card">
      <h2 style={{ marginBottom: "0.5rem", fontSize: "1.2rem" }}>
        Before you start your interview
      </h2>
      <p style={{ color: "var(--muted)", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
        This is a proctored session. Complete each step in order before proceeding.
      </p>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1.25rem",
          marginBottom: "1.5rem",
        }}
      >
        <section>
          <h3 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>
            Step 1 — Camera &amp; audio access
          </h3>
          {cameraGranted ? (
            <div className="alert success" style={{ marginTop: 0 }}>
              Camera &amp; Audio: Ready
            </div>
          ) : (
            <>
              <button
                type="button"
                className="primary"
                onClick={() => void grantCameraAccess()}
                disabled={requestingCamera}
                style={{ marginBottom: "0.75rem" }}
              >
                {requestingCamera
                  ? "Requesting access…"
                  : "Grant Camera & Audio Access"}
              </button>
              {cameraError && (
                <div className="alert error" style={{ marginTop: 0 }}>
                  {cameraError}
                </div>
              )}
            </>
          )}
        </section>

        {cameraGranted && (
          <section>
            <h3 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>
              Step 2 — Screen recording extensions &amp; camera check
            </h3>
            {checking ? (
              <div className="alert info" style={{ marginTop: 0 }}>
                Scanning for screen recording extensions and virtual cameras…
              </div>
            ) : (
              <>
                {hasExtensions ? (
                  <div className="alert error" style={{ marginTop: 0 }}>
                    {detectedExtensions.map((ext) => (
                      <p key={ext.id} style={{ marginBottom: "0.35rem" }}>
                        {extensionBlockMessage(ext)}
                      </p>
                    ))}
                  </div>
                ) : automaticScan ? (
                  <div className="alert success" style={{ marginTop: 0 }}>
                    No screen recording extensions detected.
                  </div>
                ) : (
                  <div className="alert info" style={{ marginTop: 0 }}>
                    Please confirm that no screen recording extensions (Loom,
                    Screencastify, Nimbus, etc.) are active in your browser.
                  </div>
                )}

                {virtualCamera.blockRecommended && virtualCamera.message && (
                  <div className="alert error" style={{ marginTop: "0.75rem" }}>
                    {virtualCamera.message}
                    {virtualCamera.deviceLabels.length > 0 && (
                      <ul style={{ marginTop: "0.5rem", paddingLeft: "1.25rem" }}>
                        {virtualCamera.deviceLabels.map((label) => (
                          <li key={label}>{label}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {virtualCamera.warnOnly && virtualCamera.message && (
                  <div className="alert warning" style={{ marginTop: "0.75rem" }}>
                    {virtualCamera.message}
                    {virtualCamera.deviceLabels.length > 0 && (
                      <ul style={{ marginTop: "0.5rem", paddingLeft: "1.25rem" }}>
                        {virtualCamera.deviceLabels.map((label) => (
                          <li key={label}>{label}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {screenSharingActive && (
                  <div className="alert error" style={{ marginTop: "0.75rem" }}>
                    Screen sharing is active. Stop sharing your screen before continuing.
                  </div>
                )}

                {screenSharingCapability && !screenSharingActive && (
                  <div className="alert warning" style={{ marginTop: "0.75rem" }}>
                    A screen-capture device was detected. Do not share your screen during
                    the interview — you may continue, but this will be flagged.
                  </div>
                )}
              </>
            )}
            <label
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.75rem",
                cursor: hasExtensions ? "not-allowed" : "pointer",
                color: "var(--text)",
                fontWeight: 400,
                marginTop: "0.75rem",
                opacity: hasExtensions ? 0.6 : 1,
              }}
            >
              <input
                type="checkbox"
                checked={disabledExtensions}
                onChange={(e) => setDisabledExtensions(e.target.checked)}
                disabled={hasExtensions}
                style={{
                  width: "auto",
                  marginTop: "3px",
                  accentColor: "var(--accent)",
                }}
              />
              <span>
                <strong>Disable screen recording extensions</strong> — Extensions
                like Loom, Screencastify, Nimbus, or OBS must be turned off.
              </span>
            </label>
            {!checking && (
              <button
                type="button"
                className="secondary"
                style={{ marginTop: "0.5rem" }}
                onClick={() => void runEnvironmentScan()}
              >
                Re-scan environment
              </button>
            )}
          </section>
        )}

        {cameraGranted && (
          <section>
            <h3 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>
              Step 3 — Close other tabs
            </h3>
            <label
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.75rem",
                cursor: "pointer",
                color: "var(--text)",
                fontWeight: 400,
              }}
            >
              <input
                type="checkbox"
                checked={closedTabs}
                onChange={(e) => setClosedTabs(e.target.checked)}
                style={{
                  width: "auto",
                  marginTop: "3px",
                  accentColor: "var(--accent)",
                }}
              />
              <span>
                <strong>Close other tabs &amp; windows</strong> (optional but
                recommended) — Switching tabs during the interview will trigger a
                warning.
              </span>
            </label>
          </section>
        )}

        {cameraGranted && (
          <section>
            <h3 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>
              Step 4 — Fullscreen mode
            </h3>
            <p style={{ color: "var(--muted)", fontSize: "0.9rem", marginBottom: "0.5rem" }}>
              Fullscreen is required during the interview. Enter fullscreen after
              camera access is granted.
            </p>
            {!isFullscreen ? (
              <button
                type="button"
                className="secondary"
                onClick={() => void enterFullscreen()}
              >
                Enter fullscreen
              </button>
            ) : (
              <div className="alert success" style={{ marginTop: 0 }}>
                Fullscreen active.
              </div>
            )}
          </section>
        )}

        {envVerifying && localChecksPass && (
          <div className="alert info">Verifying interview environment…</div>
        )}

        {envBlockReason && (
          <div className="alert error">{envBlockReason}</div>
        )}

        {envWarnings.length > 0 && (
          <div className="alert info">
            {envWarnings.map((w) => (
              <p key={w} style={{ marginBottom: "0.25rem" }}>
                {w}
              </p>
            ))}
          </div>
        )}
      </div>

      <div className="actions">
        <button
          className="primary"
          disabled={!canProceed}
          onClick={handleReady}
        >
          {loading ? "Starting…" : "I'm ready — Start Interview"}
        </button>
      </div>

      {!canProceed && (
        <p
          style={{
            marginTop: "0.75rem",
            fontSize: "0.8rem",
            color: "var(--muted)",
          }}
        >
          {!cameraGranted
            ? "Grant camera and audio access to continue."
            : hasExtensions
              ? "Disable detected recording extensions to continue."
              : virtualCamera.blockRecommended
                ? virtualCamera.message ?? "Use your real webcam to continue."
                : envVerifying
                  ? "Waiting for environment verification…"
                  : envAllowed === false
                    ? envBlockReason ?? "Environment check blocked starting the interview."
                    : "Complete all checklist steps (extensions, tabs, fullscreen) to enable the start button."}
        </p>
      )}
    </div>
  );
}
