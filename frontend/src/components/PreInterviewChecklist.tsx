import { useEffect, useRef, useState } from "react";
import { proctorApi } from "../api/client";
import {
  extensionBlockMessage,
  pickPreferredCameraDeviceId,
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

function getMediaErrorMessage(err: unknown): string {
  if (!window.isSecureContext) {
    return (
      "Camera and microphone require HTTPS or localhost. " +
      "On EC2 without SSL, use http://127.0.0.1:5173 locally to test, " +
      "or add HTTPS to your server for production interviews."
    );
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return "Your browser does not support camera access. Try Chrome or Edge.";
  }
  if (err instanceof DOMException) {
    switch (err.name) {
      case "NotAllowedError":
      case "PermissionDeniedError":
        return (
          "Permission denied. Click the lock or camera icon in your browser's " +
          "address bar, allow camera and microphone, then click Grant again."
        );
      case "NotFoundError":
      case "DevicesNotFoundError":
        return "No camera or microphone found. Connect a device and try again.";
      case "NotReadableError":
      case "TrackStartError":
        return (
          "Camera or microphone is busy. Close other apps using the camera " +
          "(Zoom, Teams, etc.) and try again."
        );
      case "SecurityError":
        return (
          "Browser blocked camera access on this connection. " +
          "Use https:// or test on http://localhost / http://127.0.0.1."
        );
      default:
        return err.message || "Could not access camera or microphone.";
    }
  }
  return "Camera and microphone access are required for the interview.";
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
  const previewVideoRef = useRef<HTMLVideoElement | null>(null);

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
    const video = previewVideoRef.current;
    const stream = mediaStreamRef.current;
    if (video && stream && cameraGranted) {
      video.srcObject = stream;
      void video.play().catch(() => {
        /* autoplay may need user gesture; stream is still valid */
      });
    }
    return () => {
      if (video) video.srcObject = null;
    };
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
        fullscreen_active: isFullscreen,
        selected_camera_label:
          mediaStreamRef.current?.getVideoTracks()[0]?.label || null,
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
    isFullscreen,
  ]);

  async function grantCameraAccess() {
    setRequestingCamera(true);
    setCameraError(null);

    if (!window.isSecureContext) {
      setCameraGranted(false);
      setCameraError(getMediaErrorMessage(null));
      setRequestingCamera(false);
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraGranted(false);
      setCameraError(getMediaErrorMessage(null));
      setRequestingCamera(false);
      return;
    }

    try {
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
      const preferredId = await pickPreferredCameraDeviceId();
      const stream = await navigator.mediaDevices.getUserMedia({
        video: preferredId
          ? { deviceId: { ideal: preferredId }, facingMode: "user" }
          : { facingMode: "user" },
        audio: true,
      });
      mediaStreamRef.current = stream;
      setCameraGranted(true);
    } catch (err) {
      setCameraGranted(false);
      setCameraError(getMediaErrorMessage(err));
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
      <h2 className="checklist-title">Pre-interview checks</h2>
      <p className="checklist-intro">Complete each step before starting.</p>

      <div className="invite-rules checklist-rules" role="note">
        <h3 className="invite-rules-title">Rules of engagement</h3>
        <ul className="invite-rules-list">
          <li>Quiet private room — no phone or calls</li>
          <li>Stay in fullscreen; close other tabs</li>
          <li>Do not leave the interview window until you finish</li>
        </ul>
      </div>

      <div className="checklist-steps">
        <section>
          <h3 className="checklist-step-title">1. Camera &amp; mic</h3>
          {cameraGranted ? (
            <>
              <div className="alert success alert-flush">Ready</div>
              <video
                ref={previewVideoRef}
                className="checklist-preview-video"
                autoPlay
                playsInline
                muted
              />
            </>
          ) : (
            <>
              {!window.isSecureContext && (
                <div className="alert warning alert-flush">
                  Camera needs HTTPS (or localhost).
                </div>
              )}
              <button
                type="button"
                className="primary"
                onClick={() => void grantCameraAccess()}
                disabled={requestingCamera}
                style={{ marginBottom: "0.75rem" }}
              >
                {requestingCamera
                  ? "Requesting…"
                  : "Allow camera & mic"}
              </button>
              {cameraError && (
                <div className="alert error alert-flush">{cameraError}</div>
              )}
            </>
          )}
        </section>

        {cameraGranted && (
          <section>
            <h3 className="checklist-step-title">
              2. Recording extensions &amp; camera
            </h3>
            {checking ? (
              <div className="alert info alert-flush">
                Scanning environment…
              </div>
            ) : (
              <>
                {hasExtensions ? (
                  <div className="alert error alert-flush">
                    {detectedExtensions.map((ext) => (
                      <p key={ext.id} style={{ marginBottom: "0.35rem" }}>
                        {extensionBlockMessage(ext)}
                      </p>
                    ))}
                  </div>
                ) : automaticScan ? (
                  <div className="alert success alert-flush">
                    No recording extensions detected.
                  </div>
                ) : (
                  <div className="alert info alert-flush">
                    Confirm Loom, Screencastify, Nimbus, etc. are off.
                  </div>
                )}

                {virtualCamera.blockRecommended && virtualCamera.message && (
                  <div className="alert error alert-stack">
                    {virtualCamera.message}
                    {virtualCamera.deviceLabels.length > 0 && (
                      <ul className="checklist-list">
                        {virtualCamera.deviceLabels.map((label) => (
                          <li key={label}>{label}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {virtualCamera.warnOnly && virtualCamera.message && (
                  <div className="alert warning alert-stack">
                    {virtualCamera.message}
                    {virtualCamera.deviceLabels.length > 0 && (
                      <ul className="checklist-list">
                        {virtualCamera.deviceLabels.map((label) => (
                          <li key={label}>{label}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {screenSharingActive && (
                  <div className="alert error alert-stack">
                    Stop screen sharing before continuing.
                  </div>
                )}

                {screenSharingCapability && !screenSharingActive && (
                  <div className="alert warning alert-stack">
                    Screen-capture device detected — do not share during the interview.
                  </div>
                )}
              </>
            )}
            <label
              className={`checklist-checkbox-label${hasExtensions ? " is-disabled" : ""}`}
            >
              <input
                type="checkbox"
                checked={disabledExtensions}
                onChange={(e) => setDisabledExtensions(e.target.checked)}
                disabled={hasExtensions}
              />
              <span>Recording extensions are disabled</span>
            </label>
            {!checking && (
              <button
                type="button"
                className="secondary"
                style={{ marginTop: "0.5rem" }}
                onClick={() => void runEnvironmentScan()}
              >
                Re-scan
              </button>
            )}
          </section>
        )}

        {cameraGranted && (
          <section>
            <h3 className="checklist-step-title">3. Other tabs</h3>
            <label className="checklist-checkbox-label" style={{ marginTop: 0 }}>
              <input
                type="checkbox"
                checked={closedTabs}
                onChange={(e) => setClosedTabs(e.target.checked)}
              />
              <span>Other tabs closed (tab switches are logged)</span>
            </label>
          </section>
        )}

        {cameraGranted && (
          <section>
            <h3 className="checklist-step-title">4. Fullscreen</h3>
            {!isFullscreen ? (
              <button
                type="button"
                className="secondary"
                onClick={() => void enterFullscreen()}
              >
                Enter fullscreen
              </button>
            ) : (
              <div className="alert success alert-flush">Fullscreen on</div>
            )}
          </section>
        )}

        {envVerifying && localChecksPass && (
          <div className="alert info">Verifying environment…</div>
        )}

        {envBlockReason && <div className="alert error">{envBlockReason}</div>}

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
        <button className="primary" disabled={!canProceed} onClick={handleReady}>
          {loading ? "Starting…" : "Start interview"}
        </button>
      </div>

      {!canProceed && (
        <p className="checklist-hint">
          {!cameraGranted
            ? "Allow camera and mic to continue."
            : hasExtensions
              ? "Disable recording extensions to continue."
              : virtualCamera.blockRecommended
                ? virtualCamera.message ?? "Use your real webcam to continue."
                : envVerifying
                  ? "Verifying environment…"
                  : envAllowed === false
                    ? envBlockReason ?? "Environment check blocked start."
                    : "Finish remaining checks to enable start."}
        </p>
      )}
    </div>
  );
}
