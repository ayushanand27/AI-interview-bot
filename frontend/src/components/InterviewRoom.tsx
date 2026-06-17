import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

import { interviewApi, proctorApi } from "../api/client";

import type { CurrentQuestionResponse } from "../types/interview";
import type { ProctorAnalyzeResponse } from "../types/proctor";

import { useTabSwitchDetection } from "../hooks/useTabSwitchDetection";
import { detectVirtualCamera } from "../hooks/useExtensionDetection";
import { confirmAnswerSubmit, getAnswerWarnings, MAX_ANSWER_LENGTH } from "../utils/validateAnswer";
import { startAmbientAudioMonitor } from "../utils/audioMonitor";

const LOUD_AUDIO_MESSAGE = "Please maintain a quiet environment";
const TAB_SWITCH_MESSAGE = "Tab switch detected - this has been logged";
const PROCTOR_INTERVAL_MS = 3000;
const VIRTUAL_CAMERA_CHECK_MS = 30000;
const VIOLATION_FLASH_MS = 3000;
const PROCTOR_BANNER_DISMISS_MS = 3000;
const SESSION_IDLE_MS = 15 * 60 * 1000;
const QUESTION_TIMER_SEC =
  Number(import.meta.env.VITE_QUESTION_TIMER_SECONDS) || 180;

const PROCTOR_OK_STATUSES = new Set(["ok", "calibrating"]);

function audioOnlyStream(source: MediaStream | null): MediaStream | null {
  if (!source) return null;
  const tracks = source.getAudioTracks().filter((t) => t.readyState === "live");
  if (tracks.length === 0) return null;
  return new MediaStream(tracks);
}

interface InterviewRoomProps {
  sessionId: string;
  mediaStream: MediaStream | null;
  question: CurrentQuestionResponse;
  loading: boolean;
  onSubmitAnswer: (answer: string) => void;
  onEndEarly: () => void;
  onIdleTimeout: () => void;
}

export interface InterviewRoomHandle {
  stopAndUploadRecording: () => Promise<{ uploaded: boolean }>;
}

function integrityDisplay(penaltyPercent: number): {
  label: string;
  className: string;
} {
  if (penaltyPercent <= 0) {
    return { label: "Integrity: Clean", className: "integrity-badge integrity-clean" };
  }
  if (penaltyPercent <= 10) {
    return { label: "Integrity: Flagged", className: "integrity-badge integrity-flagged" };
  }
  return {
    label: "Integrity: Flagged",
    className: "integrity-badge integrity-serious",
  };
}

export default forwardRef<InterviewRoomHandle, InterviewRoomProps>(
  function InterviewRoom(
    {
      sessionId,
      mediaStream,
      question,
      loading,
      onSubmitAnswer,
      onEndEarly,
      onIdleTimeout,
    },
    ref,
  ) {
  const [answer, setAnswer] = useState("");
  const [penaltyPercent, setPenaltyPercent] = useState(0);
  const [flashMessage, setFlashMessage] = useState<string | null>(null);
  const [proctorBanner, setProctorBanner] = useState<string | null>(null);
  const [streamWarning, setStreamWarning] = useState<string | null>(null);
  const [audioWarning, setAudioWarning] = useState<string | null>(null);
  const [transcribeNotice, setTranscribeNotice] = useState<string | null>(null);
  const [isAudioRecording, setIsAudioRecording] = useState(false);
  const [isSessionRecording, setIsSessionRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(QUESTION_TIMER_SEC);

  const answerRef = useRef("");
  const lastActivityRef = useRef(Date.now());
  const questionTimerExpiredRef = useRef(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const sessionRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const sessionChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(
    undefined,
  );
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const proctorDismissTimerRef = useRef<
    ReturnType<typeof setTimeout> | undefined
  >(undefined);
  const proctorBannerActiveRef = useRef(false);
  const ambientMicRef = useRef<MediaStream | null>(null);
  const stopAmbientMonitorRef = useRef<(() => void) | null>(null);
  const shutdownRecordingRef = useRef(false);

  const currentNum = question.question_index + 1;
  const progress =
    question.total_questions > 0
      ? (currentNum / question.total_questions) * 100
      : 0;

  const warnings = answer.trim() ? getAnswerWarnings(answer) : [];
  const integrity = integrityDisplay(penaltyPercent);

  useEffect(() => {
    answerRef.current = answer;
    lastActivityRef.current = Date.now();
  }, [answer]);

  useEffect(() => {
    setAnswer("");
    setAudioWarning(null);
    setTranscribeNotice(null);
    setSecondsLeft(QUESTION_TIMER_SEC);
    questionTimerExpiredRef.current = false;
    lastActivityRef.current = Date.now();
  }, [question.question_index]);

  const processRecordedAudio = useCallback(
    async (blob: Blob) => {
      setTranscribing(true);
      setTranscribeNotice(null);
      try {
        const res = await interviewApi.transcribeAudio(sessionId, blob);
        setAnswer(res.transcribed_text);
      } catch (err) {
        setTranscribeNotice(
          err instanceof Error ? err.message : "Failed to transcribe audio",
        );
      } finally {
        setTranscribing(false);
      }
    },
    [sessionId],
  );

  const stopAudioRecording = useCallback(() => {
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = undefined;
    }
    setIsAudioRecording(false);
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }, []);

  const stopSessionRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = sessionRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        const fallback = new Blob(sessionChunksRef.current, { type: "video/webm" });
        console.log(
          "[RECORDING] No active recorder to stop, chunks blob size:",
          fallback.size,
        );
        resolve(fallback.size > 0 ? fallback : null);
        return;
      }

      recorder.onstop = () => {
        const blob = new Blob(sessionChunksRef.current, {
          type: recorder.mimeType || "video/webm",
        });
        console.log("[RECORDING] Recording stopped, total blob size:", blob.size);
        sessionRecorderRef.current = null;
        setIsSessionRecording(false);
        resolve(blob.size > 0 ? blob : null);
      };

      if (recorder.state === "recording") {
        try {
          recorder.requestData();
        } catch (err) {
          console.log("[RECORDING] requestData failed:", err);
        }
      }

      recorder.stop();
    });
  }, []);

  const stopAndUploadRecording = useCallback(async (): Promise<{ uploaded: boolean }> => {
    shutdownRecordingRef.current = true;
    console.log("[RECORDING] stopAndUploadRecording called, session:", sessionId);

    try {
      const blob = await stopSessionRecording();

      if (!blob || blob.size < 1000) {
        console.log("[RECORDING] Blob too small, skipping upload:", blob?.size ?? 0);
        return { uploaded: false };
      }

      console.log("[RECORDING] Uploading to backend, session:", sessionId, "size:", blob.size);
      const response = await interviewApi.uploadRecording(
        sessionId,
        blob,
        "recording.webm",
      );
      console.log("[RECORDING] Upload response:", response);
      return { uploaded: true };
    } catch (err) {
      console.error("[RECORDING] Upload failed:", err);
      return { uploaded: false };
    }
  }, [sessionId, stopSessionRecording]);

  useImperativeHandle(ref, () => ({ stopAndUploadRecording }), [
    stopAndUploadRecording,
  ]);

  const startSessionRecording = useCallback((stream: MediaStream) => {
    if (sessionRecorderRef.current) return;

    const mimeType = MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")
      ? "video/webm;codecs=vp9,opus"
      : MediaRecorder.isTypeSupported("video/webm;codecs=vp8,opus")
        ? "video/webm;codecs=vp8,opus"
        : MediaRecorder.isTypeSupported("video/webm")
          ? "video/webm"
          : "";

    const recorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream);

    sessionChunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        sessionChunksRef.current.push(event.data);
        console.log(
          "[RECORDING] Chunk collected, size:",
          event.data.size,
          "total chunks:",
          sessionChunksRef.current.length,
        );
      }
    };
    recorder.start(5000);
    sessionRecorderRef.current = recorder;
    setIsSessionRecording(true);
    console.log("[RECORDING] MediaRecorder started, state:", recorder.state);
  }, []);

  const startRecording = useCallback(() => {
    if (loading || transcribing || isAudioRecording) return;
    setAudioWarning(null);
    setTranscribeNotice(null);

    const source = ambientMicRef.current ?? streamRef.current;
    const stream = audioOnlyStream(source);
    if (!stream) {
      setAudioWarning(
        "Audio recording is unavailable. Please type your answer instead.",
      );
      return;
    }

    try {
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "";

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      audioChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        mediaRecorderRef.current = null;
        if (blob.size > 0) {
          void processRecordedAudio(blob);
        } else {
          setAudioWarning("Recording was empty. Try again or type your answer.");
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsAudioRecording(true);
      setRecordingSeconds(0);
      recordingTimerRef.current = setInterval(() => {
        setRecordingSeconds((s) => s + 1);
      }, 1000);
    } catch {
      setAudioWarning(
        "Could not start audio recording. Please type your answer instead.",
      );
    }
  }, [isAudioRecording, loading, processRecordedAudio, transcribing]);

  function handleMicClick() {
    if (isAudioRecording) {
      stopAudioRecording();
    } else {
      startRecording();
    }
  }

  function handleReRecord() {
    setAnswer("");
    setAudioWarning(null);
    setTranscribeNotice(null);
    startRecording();
  }

  function formatRecordingTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  const handleProctorResponse = useCallback((res: ProctorAnalyzeResponse) => {
    setPenaltyPercent(res.score_penalty_percent ?? 0);

    const status = res.eye_status ?? "unknown";
    const isOk = PROCTOR_OK_STATUSES.has(status);

    if (!isOk) {
      if (proctorDismissTimerRef.current) {
        clearTimeout(proctorDismissTimerRef.current);
        proctorDismissTimerRef.current = undefined;
      }
      const bannerText =
        res.message?.trim() ||
        `Proctoring alert: ${status.replace(/_/g, " ")}`;
      proctorBannerActiveRef.current = true;
      setProctorBanner(bannerText);
      return;
    }

    if (proctorBannerActiveRef.current && !proctorDismissTimerRef.current) {
      proctorDismissTimerRef.current = setTimeout(() => {
        setProctorBanner(null);
        proctorBannerActiveRef.current = false;
        proctorDismissTimerRef.current = undefined;
      }, PROCTOR_BANNER_DISMISS_MS);
    }
  }, []);

  const showViolationFlash = useCallback((message: string) => {
    setFlashMessage(message);
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    flashTimerRef.current = setTimeout(() => {
      setFlashMessage(null);
    }, VIOLATION_FLASH_MS);
  }, []);

  const handleLoudAudio = useCallback(() => {
    showViolationFlash(LOUD_AUDIO_MESSAGE);
    void proctorApi
      .reportLoudAudio(sessionId, LOUD_AUDIO_MESSAGE)
      .then((res) => {
        if (res.recorded) {
          setPenaltyPercent(res.score_penalty_percent ?? 0);
        }
      })
      .catch(() => {});
  }, [sessionId, showViolationFlash]);

  const handleTabSwitch = useCallback(() => {
    showViolationFlash(TAB_SWITCH_MESSAGE);
    void proctorApi
      .reportClientViolation(sessionId, "tab_switch", TAB_SWITCH_MESSAGE)
      .then((res) => {
        if (res.recorded) {
          setPenaltyPercent(res.score_penalty_percent ?? 0);
        }
      })
      .catch(() => {});
  }, [sessionId, showViolationFlash]);

  useTabSwitchDetection({
    onWarning: handleTabSwitch,
    onTerminate: () => {},
    maxWarnings: Number.MAX_SAFE_INTEGER,
    enabled: true,
  });

  const captureAndAnalyze = useCallback(async () => {
    if (loading) return;

    const video = videoRef.current;
    if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    const base64 = dataUrl.split(",")[1];
    if (!base64) return;

    try {
      const res = await proctorApi.analyze(sessionId, base64);
      handleProctorResponse(res);
    } catch {
      // Proctoring unavailable — interview continues
    }
  }, [sessionId, loading, handleProctorResponse]);

  useEffect(() => {
    setPenaltyPercent(0);
    setFlashMessage(null);
    setProctorBanner(null);
    proctorBannerActiveRef.current = false;
    setStreamWarning(null);

    void proctorApi.reset(sessionId).catch(() => {});

    let intervalId: ReturnType<typeof setInterval> | undefined;

    function attachMedia() {
      if (!mediaStream) {
        setStreamWarning(
          "Camera feed unavailable. Return to the checklist and grant camera and microphone access.",
        );
        return;
      }

      streamRef.current = mediaStream;
      ambientMicRef.current = mediaStream;
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
        void videoRef.current.play().catch(() => {});
      }
      startSessionRecording(mediaStream);
      stopAmbientMonitorRef.current = startAmbientAudioMonitor(
        mediaStream,
        handleLoudAudio,
      );
      intervalId = setInterval(() => {
        void captureAndAnalyze();
      }, PROCTOR_INTERVAL_MS);
    }

    attachMedia();

    return () => {
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
      if (proctorDismissTimerRef.current) {
        clearTimeout(proctorDismissTimerRef.current);
      }
      stopAmbientMonitorRef.current?.();
      stopAmbientMonitorRef.current = null;
      ambientMicRef.current = null;
      if (intervalId) clearInterval(intervalId);
      if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
      const audioRecorder = mediaRecorderRef.current;
      if (audioRecorder && audioRecorder.state !== "inactive") {
        audioRecorder.stop();
      }
      if (!shutdownRecordingRef.current) {
        const sessionRec = sessionRecorderRef.current;
        if (sessionRec && sessionRec.state !== "inactive") {
          console.log("[RECORDING] Cleanup stopping session recorder");
          sessionRec.stop();
        }
      }
      streamRef.current = null;
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
    };
  }, [
    sessionId,
    mediaStream,
    captureAndAnalyze,
    handleLoudAudio,
    startSessionRecording,
  ]);

  useEffect(() => {
    async function checkVirtualCamera() {
      const result = await detectVirtualCamera(streamRef.current);
      if (!result.detected) return;

      const message =
        result.message ?? "Virtual camera detected - please use your real webcam";
      showViolationFlash(message);

      void proctorApi
        .reportClientViolation(sessionId, "virtual_camera", message)
        .then((res) => {
          if (res.recorded) {
            setPenaltyPercent(res.score_penalty_percent ?? 0);
          }
        })
        .catch(() => {});
    }

    const virtualCamIntervalId = setInterval(() => {
      void checkVirtualCamera();
    }, VIRTUAL_CAMERA_CHECK_MS);

    return () => clearInterval(virtualCamIntervalId);
  }, [sessionId, showViolationFlash]);

  useEffect(() => {
    const idleCheckId = window.setInterval(() => {
      if (Date.now() - lastActivityRef.current >= SESSION_IDLE_MS) {
        onIdleTimeout();
      }
    }, 30_000);

    return () => window.clearInterval(idleCheckId);
  }, [onIdleTimeout]);

  useEffect(() => {
    const timerId = window.setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          window.clearInterval(timerId);
          if (!questionTimerExpiredRef.current && !loading) {
            questionTimerExpiredRef.current = true;
            const trimmed = answerRef.current.trim();
            onSubmitAnswer(
              trimmed || "(No answer — time limit reached)",
            );
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => window.clearInterval(timerId);
  }, [question.question_index, loading, onSubmitAnswer]);

  function touchActivity() {
    lastActivityRef.current = Date.now();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    touchActivity();
    const trimmed = answer.trim();
    if (!trimmed || loading) return;
    if (!confirmAnswerSubmit(trimmed)) return;
    onSubmitAnswer(trimmed);
  }

  function handlePaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = e.clipboardData.getData("text");
    if (getAnswerWarnings(pasted).length > 0) {
      const ok = window.confirm(
        "You pasted content that looks like files, prompts, or long notes — not a typical interview answer.\n\nPaste anyway?",
      );
      if (!ok) e.preventDefault();
    }
  }

  return (
    <>
      {proctorBanner && (
        <div
          className="proctor-violation-banner proctor-face-warning"
          role="alert"
        >
          ⚠️ {proctorBanner}
        </div>
      )}

      {flashMessage && (
        <div className="proctor-violation-banner proctor-client-warning" role="alert">
          {flashMessage}
        </div>
      )}

      <div className="card interview-room">
        <div className="proctor-webcam-container">
          {isSessionRecording && (
            <div className="session-rec-indicator" role="status" aria-live="polite">
              <span className="session-rec-dot" aria-hidden />
              REC
            </div>
          )}
          <video
            ref={videoRef}
            className="proctor-preview"
            muted
            playsInline
            autoPlay
            aria-label="Webcam preview for proctoring"
          />
        </div>

        <div className="integrity-bar">
          <span className={integrity.className}>{integrity.label}</span>
          {penaltyPercent > 0 && (
            <span className="integrity-penalty">
              Current penalty: -{penaltyPercent}%
            </span>
          )}
        </div>

        {streamWarning && (
          <div className="alert info" style={{ marginBottom: "1rem" }}>
            {streamWarning}
          </div>
        )}

        <div className="progress">
          <span>
            Question {currentNum} of {question.total_questions}
          </span>
          <span
            className={`question-timer${secondsLeft <= 30 ? " question-timer-urgent" : ""}`}
            role="timer"
            aria-live="polite"
          >
            Time left: {Math.floor(secondsLeft / 60)}:
            {(secondsLeft % 60).toString().padStart(2, "0")}
          </span>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <p className="session-id">Session: {sessionId}</p>

        <div className="question-box">{question.question}</div>

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="answer">Your answer</label>
            <textarea
              id="answer"
              value={answer}
              onChange={(e) => {
                touchActivity();
                setAnswer(e.target.value);
              }}
              onPaste={handlePaste}
              placeholder="Type your answer, or record with the microphone…"
              required
              maxLength={MAX_ANSWER_LENGTH}
              disabled={loading || isAudioRecording || transcribing}
            />
            <p className="answer-char-count" aria-live="polite">
              {answer.length}/{MAX_ANSWER_LENGTH} characters
            </p>
            {(isAudioRecording || transcribing) && (
              <div className="recording-indicator" role="status">
                {isAudioRecording && (
                  <>
                    <span className="recording-dot" aria-hidden />
                    Recording {formatRecordingTime(recordingSeconds)}
                  </>
                )}
                {transcribing && !isAudioRecording && (
                  <span>Transcribing your answer…</span>
                )}
              </div>
            )}
            {audioWarning && (
              <div className="alert info" style={{ marginTop: "0.75rem" }}>
                {audioWarning}
              </div>
            )}
            {transcribeNotice && (
              <div className="alert info" style={{ marginTop: "0.75rem" }}>
                {transcribeNotice}
              </div>
            )}
            {warnings.length > 0 && (
              <div className="alert info" style={{ marginTop: "0.75rem" }}>
                {warnings.map((w) => (
                  <div key={w}>⚠ {w}</div>
                ))}
              </div>
            )}
          </div>

          <div className="actions">
            <button
              type="button"
              className={isAudioRecording ? "danger" : "secondary"}
              onClick={handleMicClick}
              disabled={loading || transcribing}
              title={isAudioRecording ? "Stop recording" : "Record audio answer"}
            >
              {isAudioRecording ? "Stop recording" : "Record answer"}
            </button>
            <button
              type="submit"
              className="primary"
              disabled={loading || !answer.trim() || isAudioRecording || transcribing}
            >
              {loading ? "Submitting…" : "Submit answer"}
            </button>
            {answer.trim() && !isAudioRecording && !transcribing && (
              <button
                type="button"
                className="secondary"
                onClick={handleReRecord}
                disabled={loading}
              >
                Re-record
              </button>
            )}
            <button
              type="button"
              className="secondary"
              onClick={() => setAnswer("")}
              disabled={loading || !answer.trim() || isAudioRecording || transcribing}
            >
              Clear answer
            </button>
            <button
              type="button"
              className="danger"
              onClick={onEndEarly}
              disabled={loading}
            >
              End interview early
            </button>
          </div>
        </form>
      </div>
    </>
  );
},
);
