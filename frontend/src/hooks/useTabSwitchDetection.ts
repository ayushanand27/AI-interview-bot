// frontend/src/hooks/useTabSwitchDetection.ts
import { useEffect, useRef } from "react";

/** Ignore brief focus flickers (Alt-Tab bounce, OS overlays). */
const BLUR_DEBOUNCE_MS = 400;
/** Align with backend WarningManager.COOLDOWN_SECONDS and audio monitor. */
const REPORT_COOLDOWN_MS = 15_000;

interface UseTabSwitchDetectionProps {
  onWarning: (count: number) => void;
  onTerminate: () => void;
  maxWarnings?: number;
  enabled?: boolean;
}

/**
 * Detects leaving the interview surface:
 * - Tab switch / minimized: `visibilitychange` when `document.hidden`
 * - Side-by-side window / other app: `window` blur (split-screen stays "visible")
 *
 * Does not terminate the interview; callers log + apply integrity penalty.
 */
export function useTabSwitchDetection({
  onWarning,
  onTerminate,
  maxWarnings = 3,
  enabled = true,
}: UseTabSwitchDetectionProps) {
  const warningCount = useRef(0);
  const lastReportAt = useRef(0);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );

  const onWarningRef = useRef(onWarning);
  const onTerminateRef = useRef(onTerminate);

  useEffect(() => {
    onWarningRef.current = onWarning;
  }, [onWarning]);

  useEffect(() => {
    onTerminateRef.current = onTerminate;
  }, [onTerminate]);

  useEffect(() => {
    if (!enabled) return;

    function reportFocusLoss(opts?: { fromVisibility?: boolean }) {
      const now = Date.now();
      if (now - lastReportAt.current < REPORT_COOLDOWN_MS) {
        return;
      }
      // Debounced blur only — skip if focus already returned.
      // visibilitychange (hidden) is authoritative even if hasFocus is flaky.
      if (
        !opts?.fromVisibility &&
        typeof document.hasFocus === "function" &&
        document.hasFocus()
      ) {
        return;
      }

      lastReportAt.current = now;
      warningCount.current += 1;
      if (warningCount.current >= maxWarnings) {
        onTerminateRef.current();
      } else {
        onWarningRef.current(warningCount.current);
      }
    }

    function clearBlurTimer() {
      if (blurTimer.current !== undefined) {
        clearTimeout(blurTimer.current);
        blurTimer.current = undefined;
      }
    }

    function handleVisibilityChange() {
      if (document.hidden) {
        clearBlurTimer();
        reportFocusLoss({ fromVisibility: true });
      }
    }

    function handleWindowBlur() {
      clearBlurTimer();
      blurTimer.current = setTimeout(() => {
        blurTimer.current = undefined;
        reportFocusLoss();
      }, BLUR_DEBOUNCE_MS);
    }

    function handleWindowFocus() {
      clearBlurTimer();
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("blur", handleWindowBlur);
    window.addEventListener("focus", handleWindowFocus);

    return () => {
      clearBlurTimer();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("blur", handleWindowBlur);
      window.removeEventListener("focus", handleWindowFocus);
    };
  }, [enabled, maxWarnings]);

  return { warningCount: warningCount.current };
}
