/** Detect phones/tablets — enterprise proctoring platforms require desktop. */

export function isMobileDevice(): boolean {
  if (typeof navigator === "undefined") return false;

  const ua = navigator.userAgent || navigator.vendor || "";
  if (/android|iphone|ipad|ipod|mobile|webos|blackberry|iemobile|opera mini/i.test(ua)) {
    return true;
  }

  const coarse = window.matchMedia("(max-width: 768px) and (hover: none) and (pointer: coarse)");
  return coarse.matches;
}
