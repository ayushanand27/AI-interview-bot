import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Editor from "@monaco-editor/react";

import { interviewApi, proctorApi } from "../api/client";

import type { CurrentQuestionResponse } from "../types/interview";
import type { ProctorAnalyzeResponse } from "../types/proctor";

import { useTabSwitchDetection } from "../hooks/useTabSwitchDetection";
import {
  detectScreenRecordingExtensions,
  detectScreenSharingActive,
  detectVirtualCamera,
} from "../hooks/useExtensionDetection";
import { confirmAnswerSubmit, getAnswerWarnings, MAX_ANSWER_LENGTH } from "../utils/validateAnswer";
import { startAmbientAudioMonitor } from "../utils/audioMonitor";
import {
  CONFIDENTIAL_FOOTER,
  attachInterviewClipboardGuards,
  wrapQuestionWithCanary,
} from "../utils/antiCheat";

const MONACO_LANG: Record<string, string> = {
  python: "python",
  javascript: "javascript",
  java: "java",
  cpp: "cpp",
  c: "c",
  perl: "plaintext",
};

const LOUD_AUDIO_MESSAGE = "Please maintain a quiet environment";
const TAB_SWITCH_MESSAGE =
  "Switched away from interview window - this has been logged";
const PROCTOR_INTERVAL_MS = 3000;
const VIRTUAL_CAMERA_CHECK_MS = 30000;
const ENVIRONMENT_CHECK_MS = 20000;
const VIOLATION_FLASH_MS = 3000;
const PROCTOR_BANNER_DISMISS_MS = 3000;
const SESSION_IDLE_MS = 15 * 60 * 1000;
const QUESTION_TIMER_SEC =
  Number(import.meta.env.VITE_QUESTION_TIMER_SECONDS) || 180;

const PROCTOR_OK_STATUSES = new Set(["ok", "calibrating"]);

/** Keep PiP clear of banners (top) and primary action buttons (bottom). */
const PIP_SAFE_TOP = 72;
const PIP_SAFE_BOTTOM = 104;
const PIP_SAFE_EDGE = 16;
const PIP_DEFAULT_W = 200;
const PIP_DEFAULT_H = 150;

function clampPipPosition(
  left: number,
  top: number,
  width = PIP_DEFAULT_W,
  height = PIP_DEFAULT_H,
): { left: number; top: number } {
  const maxLeft = Math.max(
    PIP_SAFE_EDGE,
    window.innerWidth - width - PIP_SAFE_EDGE,
  );
  const maxTop = Math.max(
    PIP_SAFE_TOP,
    window.innerHeight - height - PIP_SAFE_BOTTOM,
  );
  return {
    left: Math.min(Math.max(PIP_SAFE_EDGE, left), maxLeft),
    top: Math.min(Math.max(PIP_SAFE_TOP, top), maxTop),
  };
}

function defaultPipPosition(
  width = PIP_DEFAULT_W,
  height = PIP_DEFAULT_H,
): { left: number; top: number } {
  return clampPipPosition(
    window.innerWidth - width - PIP_SAFE_EDGE,
    PIP_SAFE_TOP,
    width,
    height,
  );
}

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
  onSubmitCodingAnswer: (language: string, source: string) => void;
  onEndEarly: () => void;
  onIdleTimeout: () => void;
  candidateEmail?: string | null;
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
      onSubmitCodingAnswer,
      onEndEarly,
      onIdleTimeout,
      candidateEmail,
    },
    ref,
  ) {
  const [answer, setAnswer] = useState("");
  const [selectedOptions, setSelectedOptions] = useState<string[]>([]);
  const [codingLanguage, setCodingLanguage] = useState("python");
  const [codingSource, setCodingSource] = useState("");
  const [codingRunning, setCodingRunning] = useState(false);
  const [codingRunResult, setCodingRunResult] = useState<{
    passed: number;
    total: number;
    error?: string | null;
    cases: Array<{
      passed: boolean;
      status: string;
      stdin: string;
      expected_stdout: string;
      actual_stdout: string;
      stderr?: string;
    }>;
  } | null>(null);
  const codingSourceRef = useRef("");
  const codingLanguageRef = useRef("python");
  const [contentObscured, setContentObscured] = useState(false);
  const [watermarkClock, setWatermarkClock] = useState(() =>
    new Date().toLocaleString(),
  );
  const roomRootRef = useRef<HTMLDivElement | null>(null);
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
  const [secondsLeft, setSecondsLeft] = useState(
    question.time_seconds && question.time_seconds > 0
      ? question.time_seconds
      : QUESTION_TIMER_SEC,
  );

  const answerRef = useRef("");
  const selectedOptionsRef = useRef<string[]>([]);
  const lastActivityRef = useRef(Date.now());
  const questionTimerExpiredRef = useRef(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const pipContainerRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [pipPos, setPipPos] = useState<{ left: number; top: number } | null>(
    null,
  );
  const [isPipDragging, setIsPipDragging] = useState(false);
  const pipDragRef = useRef<{
    pointerId: number;
    offsetX: number;
    offsetY: number;
    width: number;
    height: number;
  } | null>(null);
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
  const qType = (question.question_type || "subjective").toLowerCase();
  const isObjective = qType === "mcq" || qType === "msq" || qType === "numerical";
  const isCoding = qType === "coding";
  const questionOptions = question.options ?? [];
  const codingLanguages =
    question.languages && question.languages.length > 0
      ? question.languages
      : ["python"];
  const watermarkLine = [
    candidateEmail?.trim() || "candidate",
    `session:${sessionId.slice(0, 8)}`,
    watermarkClock,
  ].join(" · ");
  const displayQuestion = question.question || "";
  const canaryPayload = question.question
    ? wrapQuestionWithCanary("", sessionId).trim()
    : "";

  useEffect(() => {
    answerRef.current = answer;
    lastActivityRef.current = Date.now();
  }, [answer]);

  useEffect(() => {
    selectedOptionsRef.current = selectedOptions;
  }, [selectedOptions]);

  useEffect(() => {
    setAnswer("");
    setSelectedOptions([]);
    setAudioWarning(null);
    setTranscribeNotice(null);
    setCodingRunResult(null);
    const langs =
      question.languages && question.languages.length > 0
        ? question.languages
        : ["python"];
    const lang = langs[0];
    setCodingLanguage(lang);
    const starter =
      question.starter_code?.[lang] ||
      question.starter_code?.[langs[0]] ||
      "";
    setCodingSource(starter);
    codingSourceRef.current = starter;
    codingLanguageRef.current = lang;
    const timerSec =
      question.time_seconds && question.time_seconds > 0
        ? question.time_seconds
        : QUESTION_TIMER_SEC;
    setSecondsLeft(timerSec);
    questionTimerExpiredRef.current = false;
    lastActivityRef.current = Date.now();
  }, [question.question_index, question.time_seconds, question.question_type, question.languages, question.starter_code]);

  useEffect(() => {
    codingSourceRef.current = codingSource;
  }, [codingSource]);

  useEffect(() => {
    codingLanguageRef.current = codingLanguage;
  }, [codingLanguage]);

  useEffect(() => {
    const id = window.setInterval(() => {
      setWatermarkClock(new Date().toLocaleString());
    }, 15_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const root = roomRootRef.current;
    if (!root) return;
    return attachInterviewClipboardGuards(root, () => {
      setFlashMessage("Copy / paste is disabled during the interview");
      window.setTimeout(() => setFlashMessage(null), 2000);
    });
  }, []);

  useEffect(() => {
    function syncObscure() {
      const hidden = document.hidden || !document.hasFocus();
      setContentObscured(hidden);
    }
    function onBlur() {
      window.setTimeout(syncObscure, 200);
    }
    document.addEventListener("visibilitychange", syncObscure);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", syncObscure);
    syncObscure();
    return () => {
      document.removeEventListener("visibilitychange", syncObscure);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", syncObscure);
    };
  }, []);

  function resolveSubmitPayload(): string | null {
    if (qType === "mcq") {
      return selectedOptions[0]?.trim() || null;
    }
    if (qType === "msq") {
      if (selectedOptions.length === 0) return null;
      return JSON.stringify([...selectedOptions].sort());
    }
    if (qType === "numerical") {
      return answer.trim() || null;
    }
    return answer.trim() || null;
  }

  function toggleOption(option: string) {
    lastActivityRef.current = Date.now();
    if (qType === "mcq") {
      setSelectedOptions([option]);
      return;
    }
    setSelectedOptions((prev) =>
      prev.includes(option)
        ? prev.filter((o) => o !== option)
        : [...prev, option],
    );
  }

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

  const showViolationFlash = useCallback((message: string) => {
    setFlashMessage(message);
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    flashTimerRef.current = setTimeout(() => {
      setFlashMessage(null);
    }, VIOLATION_FLASH_MS);
  }, []);

  const handleProctorResponse = useCallback((res: ProctorAnalyzeResponse) => {
    setPenaltyPercent(res.score_penalty_percent ?? 0);

    const alert = res.alert_message?.trim();
    if (alert) {
      showViolationFlash(alert);
    }

    const status = res.eye_status ?? "unknown";
    const isOk = PROCTOR_OK_STATUSES.has(status);

    if (!isOk || res.violation_type === "prohibited_object_detected") {
      if (proctorDismissTimerRef.current) {
        clearTimeout(proctorDismissTimerRef.current);
        proctorDismissTimerRef.current = undefined;
      }
      const bannerText =
        alert ||
        res.message?.trim() ||
        `Proctoring alert: ${(res.violation_type || status).replace(/_/g, " ")}`;
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
  }, [showViolationFlash]);

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
    const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
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

  // Viewport-fixed PiP (must live outside .card — backdrop-filter traps position:fixed).
  useEffect(() => {
    const measure = () => {
      const el = pipContainerRef.current;
      const width = el?.offsetWidth || PIP_DEFAULT_W;
      const height = el?.offsetHeight || PIP_DEFAULT_H;
      setPipPos((prev) =>
        prev
          ? clampPipPosition(prev.left, prev.top, width, height)
          : defaultPipPosition(width, height),
      );
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  // Keep the live preview attached even if the overlay remounts.
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !mediaStream) return;
    if (video.srcObject !== mediaStream) {
      video.srcObject = mediaStream;
    }
    void video.play().catch(() => {});
  }, [mediaStream]);

  // Never use browser native PiP — it leaves a black "Playing in picture-in-picture"
  // placeholder over the original video (often covering End Interview).
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const kickNativePip = () => {
      if (document.pictureInPictureElement === video) {
        void document.exitPictureInPicture().catch(() => {});
      }
      void video.play().catch(() => {});
    };

    video.addEventListener("enterpictureinpicture", kickNativePip);
    document.addEventListener("enterpictureinpicture", kickNativePip);
    kickNativePip();

    return () => {
      video.removeEventListener("enterpictureinpicture", kickNativePip);
      document.removeEventListener("enterpictureinpicture", kickNativePip);
    };
  }, [mediaStream]);

  function handlePipPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    const el = pipContainerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    pipDragRef.current = {
      pointerId: e.pointerId,
      offsetX: e.clientX - rect.left,
      offsetY: e.clientY - rect.top,
      width: rect.width,
      height: rect.height,
    };
    el.setPointerCapture(e.pointerId);
    setIsPipDragging(true);
  }

  function handlePipPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const drag = pipDragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    setPipPos(
      clampPipPosition(
        e.clientX - drag.offsetX,
        e.clientY - drag.offsetY,
        drag.width,
        drag.height,
      ),
    );
  }

  function handlePipPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    const drag = pipDragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    pipDragRef.current = null;
    setIsPipDragging(false);
    try {
      pipContainerRef.current?.releasePointerCapture(e.pointerId);
    } catch {
      // already released
    }
  }

  useEffect(() => {
    async function checkVirtualCamera() {
      const result = await detectVirtualCamera(streamRef.current);
      if (!result.blockRecommended) return;

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
    const reportedExtensions = new Set<string>();

    async function checkEnvironmentIntegrity() {
      const stream = streamRef.current;

      if (detectScreenSharingActive(stream)) {
        const message = "Screen sharing detected during interview";
        showViolationFlash(message);
        void proctorApi
          .reportClientViolation(sessionId, "screen_sharing", message)
          .then((res) => {
            if (res.recorded) {
              setPenaltyPercent(res.score_penalty_percent ?? 0);
            }
          })
          .catch(() => {});
      }

      const extensionScan = await detectScreenRecordingExtensions();
      for (const ext of extensionScan.detected) {
        if (reportedExtensions.has(ext.id)) continue;
        reportedExtensions.add(ext.id);

        const message = `Recording extension detected during interview: ${ext.name}`;
        showViolationFlash(message);
        void proctorApi
          .reportClientViolation(sessionId, "recording_extension", message)
          .then((res) => {
            if (res.recorded) {
              setPenaltyPercent(res.score_penalty_percent ?? 0);
            }
          })
          .catch(() => {});
      }
    }

    const envIntervalId = setInterval(() => {
      void checkEnvironmentIntegrity();
    }, ENVIRONMENT_CHECK_MS);

    void checkEnvironmentIntegrity();

    return () => clearInterval(envIntervalId);
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
            const type = (question.question_type || "subjective").toLowerCase();
            let payload = "(No answer — time limit reached)";
            if (type === "mcq") {
              payload =
                selectedOptionsRef.current[0]?.trim() ||
                "(No answer — time limit reached)";
              onSubmitAnswer(payload);
            } else if (type === "msq") {
              payload =
                selectedOptionsRef.current.length > 0
                  ? JSON.stringify([...selectedOptionsRef.current].sort())
                  : "(No answer — time limit reached)";
              onSubmitAnswer(payload);
            } else if (type === "coding") {
              const src = codingSourceRef.current.trim();
              onSubmitCodingAnswer(
                codingLanguageRef.current,
                src || "// No answer — time limit reached\n",
              );
            } else {
              const trimmed = answerRef.current.trim();
              payload = trimmed || "(No answer — time limit reached)";
              onSubmitAnswer(payload);
            }
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => window.clearInterval(timerId);
  }, [question.question_index, loading, onSubmitAnswer, onSubmitCodingAnswer]);

  function touchActivity() {
    lastActivityRef.current = Date.now();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    touchActivity();
    if (isCoding) {
      const src = codingSource.trim();
      if (!src || loading || codingRunning) return;
      onSubmitCodingAnswer(codingLanguage, src);
      return;
    }
    const payload = resolveSubmitPayload();
    if (!payload || loading) return;
    if (!isObjective && !confirmAnswerSubmit(payload)) return;
    onSubmitAnswer(payload);
  }

  async function handleRunPublicTests() {
    touchActivity();
    const src = codingSource.trim();
    if (!src || loading || codingRunning) return;
    setCodingRunning(true);
    setCodingRunResult(null);
    try {
      const result = await interviewApi.runCodingPublicTests(
        sessionId,
        codingLanguage,
        src,
      );
      setCodingRunResult(result);
    } catch (err) {
      setCodingRunResult({
        passed: 0,
        total: question.public_tests?.length ?? 0,
        error: err instanceof Error ? err.message : "Run failed",
        cases: [],
      });
    } finally {
      setCodingRunning(false);
    }
  }

  function changeCodingLanguage(lang: string) {
    touchActivity();
    setCodingLanguage(lang);
    const starter = question.starter_code?.[lang];
    if (starter != null && !codingSource.trim()) {
      setCodingSource(starter);
    } else if (starter != null && codingSource === (question.starter_code?.[codingLanguage] || "")) {
      setCodingSource(starter);
    }
  }

  const pipPreview =
    typeof document !== "undefined"
      ? createPortal(
          <div
            ref={pipContainerRef}
            className={`proctor-webcam-container${isPipDragging ? " is-dragging" : ""}`}
            style={
              pipPos
                ? {
                    left: pipPos.left,
                    top: pipPos.top,
                    right: "auto",
                    bottom: "auto",
                  }
                : undefined
            }
            onPointerDown={handlePipPointerDown}
            onPointerMove={handlePipPointerMove}
            onPointerUp={handlePipPointerUp}
            onPointerCancel={handlePipPointerUp}
            title="Drag to reposition camera preview"
            role="group"
            aria-label="Draggable webcam preview"
          >
            {isSessionRecording && (
              <div
                className="session-rec-indicator"
                role="status"
                aria-live="polite"
              >
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
              disablePictureInPicture
              disableRemotePlayback
              controlsList="nodownload nofullscreen noremoteplayback"
              aria-label="Webcam preview for proctoring"
            />
          </div>,
          document.body,
        )
      : null;

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

      {pipPreview}

      <div className="card interview-room" ref={roomRootRef}>
        <div className="integrity-bar">
          <span className={integrity.className}>{integrity.label}</span>
          {penaltyPercent > 0 && (
            <span className="integrity-penalty">
              Current penalty: -{penaltyPercent}%
            </span>
          )}
        </div>

        {streamWarning && (
          <div className="alert info alert-inline">
            {streamWarning}
          </div>
        )}

        <div className="progress">
          <span>
            Question {currentNum} of {question.total_questions}
            {question.marks != null && (
              <span className="question-marks"> · {question.marks} marks</span>
            )}
            {question.is_adaptive_follow_up && (
              <span className="question-adaptive-badge" title="Adapted from your previous answer">
                {" "}
                · Follow-up
                {question.adaptive_topic ? ` · ${question.adaptive_topic}` : ""}
              </span>
            )}
            {isObjective && (
              <span className="question-type-tag"> · {qType.toUpperCase()}</span>
            )}
            {isCoding && (
              <span className="question-type-tag"> · CODING</span>
            )}
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

        <div
          className={`question-box anti-leak-pane${contentObscured ? " is-obscured" : ""}`}
        >
          <div className="question-watermark" aria-hidden="true">
            {Array.from({ length: 12 }).map((_, i) => (
              <span key={i}>{watermarkLine}</span>
            ))}
          </div>
          <div className="question-text-protected user-select-none">
            {displayQuestion}
            {canaryPayload && (
              <span className="ai-canary-hidden" aria-hidden="true">
                {canaryPayload}
              </span>
            )}
          </div>
          <p className="question-confidential-footer">{CONFIDENTIAL_FOOTER}</p>
          {contentObscured && (
            <div className="question-obscure-overlay" role="status">
              Return focus to continue — question hidden while away
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit}>
          {(qType === "mcq" || qType === "msq") && (
            <div className="field objective-options">
              <label>
                {qType === "mcq"
                  ? "Select one answer"
                  : "Select all that apply"}
              </label>
              <div className="option-list">
                {questionOptions.map((opt) => {
                  const checked = selectedOptions.includes(opt);
                  return (
                    <label
                      key={opt}
                      className={`option-choice${checked ? " is-selected" : ""}`}
                    >
                      <input
                        type={qType === "mcq" ? "radio" : "checkbox"}
                        name="objective-answer"
                        checked={checked}
                        onChange={() => toggleOption(opt)}
                        disabled={loading}
                      />
                      <span>{opt}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {qType === "numerical" && (
            <div className="field">
              <label htmlFor="answer">Your numerical answer</label>
              <input
                id="answer"
                type="text"
                inputMode="decimal"
                value={answer}
                onChange={(e) => {
                  touchActivity();
                  setAnswer(e.target.value);
                }}
                onCopy={(e) => e.preventDefault()}
                onCut={(e) => e.preventDefault()}
                onPaste={(e) => e.preventDefault()}
                placeholder="Enter a number"
                required
                disabled={loading}
                className="numerical-answer-input"
              />
              {question.tolerance != null && question.tolerance > 0 && (
                <p className="answer-char-count">
                  Tolerance allowed: +/-{question.tolerance}
                </p>
              )}
            </div>
          )}

          {isCoding && (
            <div className="field coding-editor-field">
              <div className="coding-toolbar">
                <label>
                  Language
                  <select
                    value={codingLanguage}
                    disabled={loading || codingRunning}
                    onChange={(e) => changeCodingLanguage(e.target.value)}
                  >
                    {codingLanguages.map((lang) => (
                      <option key={lang} value={lang}>
                        {lang}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="secondary"
                  disabled={loading || codingRunning || !codingSource.trim()}
                  onClick={() => void handleRunPublicTests()}
                >
                  {codingRunning ? "Running…" : "Run public tests"}
                </button>
              </div>
              {(question.public_tests?.length ?? 0) > 0 && (
                <details className="coding-sample-tests">
                  <summary>
                    Sample tests ({question.public_tests?.length})
                  </summary>
                  <ul>
                    {(question.public_tests ?? []).map((t, idx) => (
                      <li key={idx}>
                        <pre>stdin: {t.stdin || "(empty)"}</pre>
                        <pre>expected: {t.expected_stdout || "(empty)"}</pre>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <div className="coding-monaco-wrap">
                <Editor
                  height="320px"
                  language={MONACO_LANG[codingLanguage] || "plaintext"}
                  theme="vs-dark"
                  value={codingSource}
                  onChange={(value) => {
                    touchActivity();
                    setCodingSource(value ?? "");
                  }}
                  options={{
                    minimap: { enabled: false },
                    fontSize: 14,
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                    tabSize: 2,
                  }}
                />
              </div>
              {codingRunResult && (
                <div className="coding-run-results" role="status">
                  <p>
                    Public tests:{" "}
                    <strong>
                      {codingRunResult.passed}/{codingRunResult.total}
                    </strong>{" "}
                    passed
                    {codingRunResult.error ? ` — ${codingRunResult.error}` : ""}
                  </p>
                  <ul>
                    {codingRunResult.cases.map((c, idx) => (
                      <li key={idx} className={c.passed ? "pass" : "fail"}>
                        Case {idx + 1}: {c.passed ? "PASS" : "FAIL"} ({c.status})
                        {!c.passed && (
                          <pre>
                            expected: {c.expected_stdout}
                            {"\n"}got: {c.actual_stdout}
                            {c.stderr ? `\nstderr: ${c.stderr}` : ""}
                          </pre>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {qType === "subjective" && (
            <div className="field">
              <label htmlFor="answer">Your answer</label>
              <textarea
                id="answer"
                value={answer}
                onChange={(e) => {
                  touchActivity();
                  setAnswer(e.target.value);
                }}
                onCopy={(e) => e.preventDefault()}
                onCut={(e) => e.preventDefault()}
                onPaste={(e) => e.preventDefault()}
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
                <div className="alert info alert-stack">
                  {audioWarning}
                </div>
              )}
              {transcribeNotice && (
                <div className="alert info alert-stack">
                  {transcribeNotice}
                </div>
              )}
              {warnings.length > 0 && (
                <div className="alert info alert-stack">
                  {warnings.map((w) => (
                    <div key={w}>⚠ {w}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="actions">
            {qType === "subjective" && (
              <button
                type="button"
                className={isAudioRecording ? "danger" : "secondary"}
                onClick={handleMicClick}
                disabled={loading || transcribing}
                title={isAudioRecording ? "Stop recording" : "Record audio answer"}
              >
                {isAudioRecording ? "Stop recording" : "Record answer"}
              </button>
            )}
            <button
              type="submit"
              className="primary"
              disabled={
                loading ||
                codingRunning ||
                isAudioRecording ||
                transcribing ||
                (isCoding
                  ? !codingSource.trim()
                  : !resolveSubmitPayload())
              }
            >
              {loading
                ? "Submitting…"
                : isCoding
                  ? "Submit code"
                  : "Submit answer"}
            </button>
            {qType === "subjective" &&
              answer.trim() &&
              !isAudioRecording &&
              !transcribing && (
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
              onClick={() => {
                setAnswer("");
                setSelectedOptions([]);
              }}
              disabled={
                loading ||
                (!answer.trim() && selectedOptions.length === 0) ||
                isAudioRecording ||
                transcribing
              }
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
