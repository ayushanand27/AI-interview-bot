// frontend/src/hooks/useTabSwitchDetection.ts
import { useEffect, useRef } from "react";

interface UseTabSwitchDetectionProps {
  onWarning: (count: number) => void;
  onTerminate: () => void;
  maxWarnings?: number;
  enabled?: boolean;
}

export function useTabSwitchDetection({
  onWarning,
  onTerminate,
  maxWarnings = 3,
  enabled = true,
}: UseTabSwitchDetectionProps) {
  const warningCount = useRef(0);

  // Store callbacks in refs so the event listener always
  // calls the latest version — avoids stale closure bugs
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

    function handleVisibilityChange() {
      if (document.hidden) {
        warningCount.current += 1;
        if (warningCount.current >= maxWarnings) {
          onTerminateRef.current();
        } else {
          onWarningRef.current(warningCount.current);
        }
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [enabled, maxWarnings]);

  return { warningCount: warningCount.current };
}